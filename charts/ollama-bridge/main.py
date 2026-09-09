import os
import json
import logging
import requests
import threading
import asyncio
import ssl
import aiohttp
from fastapi import FastAPI
from urllib.parse import urlparse

# ==========================================
# SSL CONTEXT FOR PYTHON 3.11
# ==========================================
# Globally relaxes hostname checks and certificate verification for internal cluster routing.
_orig_create_default_context = ssl.create_default_context
def _patched_create_default_context(*args, **kwargs):
    kwargs["purpose"] = ssl.Purpose.SERVER_AUTH
    ctx = _orig_create_default_context(*args, **kwargs)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx
ssl.create_default_context = _patched_create_default_context

# Set logging format for container observability
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI application 
app = FastAPI(title="Mattermost Ollama Bridge")

# ==========================================
# CONFIGURATION & ENVIRONMENT VARIABLES
# ==========================================
OLLAMA_HOST = os.environ["OLLAMA_HOST"]
MATTERMOST_URL = os.environ["MATTERMOST_URL"]

# Read timeout from environment, default to 188 seconds if not set
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", 60))

# Parse Mattermost URL components for API endpoints or fallback to standard strings
parsed_url = urlparse(MATTERMOST_URL)
scheme = parsed_url.scheme or "http"
hostname = parsed_url.hostname or "mattermost-team-edition"
port = parsed_url.port or 8065

# Load comma-separated list of Mattermost bot tokens
raw_tokens = os.getenv("MATTERMOST_BOT_TOKENS", "")
BOT_TOKENS = [t.strip() for t in raw_tokens.split(",") if t.strip()]

# Load comma-separated list of Ollama models, defaulting safely to fist model in list or 404 is list is empty
raw_models = os.getenv("OLLAMA_MODELS", os.getenv("OLLAMA_MODEL", "default-model"))
MODEL_LIST = [m.strip() for m in raw_models.split(",") if m.strip()]
DEFAULT_MODEL = MODEL_LIST[0] if MODEL_LIST else "default-model"

# Map each bot token 1-to-1 with its corresponding Ollama model
TOKEN_MODEL_MAP = dict(zip(BOT_TOKENS, MODEL_LIST))

# Startup debug log to verify proper pairing of tokens and models
for token, model in TOKEN_MODEL_MAP.items():
    logger.info(f"DEBUG: Mapped token {token[:6]}... to model '{model}'")

# Track active bot user IDs fetched from Mattermost to prevent infinite message loops
BOT_USER_IDS = set()

# ==========================================
# BOT USER INITIALIZATION
# ==========================================
# Validates the bot token against Mattermost API and retrieves its unique User ID.
# This ID is stored in BOT_USER_IDS so the bot knows to ignore its own messages.
def fetch_bot_user_id(token):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        res = requests.get(f"{MATTERMOST_URL}/api/v4/users/me", headers=headers, timeout=10)
        
        if res.status_code != 200:
            logger.error(f"FAIL: Token {token[:6]}... returned status {res.status_code}: {res.text}")
            return
            
        user_id = res.json().get("id")
        if user_id:
            BOT_USER_IDS.add(user_id)
            model_assigned = TOKEN_MODEL_MAP.get(token, DEFAULT_MODEL)
            logger.info(f"Registered bot user ID {user_id} with model '{model_assigned}'")
        else:
            logger.error(f"Response for token {token[:6]}... did not contain an 'id'")
    except Exception as e:
        logger.error(f"Exception while fetching bot user ID for token {token[:6]}...: {e}", exc_info=True)

# ==========================================
# MESSAGE PROCESSING & OLLAMA BRIDGE LOGIC
# ==========================================
# Parses incoming WebSocket message events, screens out bot self-messages,
# queries the Ollama backend using the assigned model, and posts the reply back to Mattermost.
def handle_post(message, token):
    event_data = json.loads(message) if isinstance(message, str) else message
    if event_data.get("event") != "posted":
        return

    data = event_data.get("data", {})
    post_raw = data.get("post")
    if isinstance(post_raw, str):
        post = json.loads(post_raw)
    else:
        post = post_raw
        
    if not post:
        return
        
    # Ignore messages sent by any managed bot user to prevent endless conversation loops
    sender_id = post.get("user_id")
    if sender_id in BOT_USER_IDS:
        return
        
    message_text = post.get("message", "")
    channel_id = post.get("channel_id")
    
    if not message_text:
        return

    # Look up the specific model mapped to this bot token
    assigned_model = TOKEN_MODEL_MAP.get(token, DEFAULT_MODEL)
    logger.info(f"Received message in channel {channel_id} (Model: {assigned_model}): {message_text}")
    
    # Send prompt to Ollama backend API
    try:
        ollama_res = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": assigned_model, "prompt": message_text, "stream": False},
            timeout=OLLAMA_TIMEOUT
        )
        ollama_res.raise_for_status()
        answer = ollama_res.json().get("response", "No response generated.")
    except Exception as e:
        logger.error(f"Error querying Ollama ({assigned_model}): {e}")
        answer = f"Error communicating with Ollama ({assigned_model}): {str(e)}"
        
    # Post the generated response back to the Mattermost channel using the specific bot token
    post_url = f"{MATTERMOST_URL}/api/v4/posts"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "channel_id": channel_id,
        "message": answer,
        # "root_id": post.get("id")  # Uncomment if you want responses threaded to the original message
    }
    try:
        res = requests.post(post_url, json=payload, headers=headers)
        res.raise_for_status()
        logger.info(f"Successfully posted response back to Mattermost using bot token.")
    except Exception as e:
        logger.error(f"Failed to post reply to Mattermost: {e}")

# ==========================================
# ASYNCHRONOUS WEBSOCKET CLIENT LISTENER
# ==========================================
# Main asynchronous loop maintaining an active WebSocket connection to Mattermost 
# for a specific bot token. Handles authentication challenge and event streaming.
async def run_bot_async(token):
    ws_scheme = "wss" if scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{hostname}:{port}{parsed_url.path.rstrip('/')}/api/v4/websocket"

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    assigned_model = TOKEN_MODEL_MAP.get(token, DEFAULT_MODEL)

    while True:
        try:
            logger.info(f"Connecting bot ({assigned_model}) to WebSocket at {ws_url}...")
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url, ssl=ssl_context) as ws:
                    # Mattermost authentication handshake payload
                    auth_payload = {
                        "seq": 1,
                        "action": "authentication_challenge",
                        "data": {"token": token}
                    }
                    await ws.send_json(auth_payload)
                    logger.info(f"Bot ({assigned_model}) WebSocket connected and authenticated.")

                    # Listen for incoming real-time events from the WebSocket stream
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                                if isinstance(data, dict) and data.get("status") == "FAIL":
                                    logger.error(f"Mattermost reported FAIL status for bot ({assigned_model}): {data}")

                                handle_post(msg.data, token)
                            except Exception as e:
                                logger.error(f"Error handling post event for bot ({assigned_model}): {e}", exc_info=True)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                            logger.warning(f"WebSocket closed by server for bot ({assigned_model}). Close code: {ws.close_code}")
                            break
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error(f"WebSocket error encountered for bot ({assigned_model}): {ws.exception()}")
                            break
        except Exception as e:
            logger.error(f"WebSocket connection error for bot ({assigned_model}): {e}. Reconnecting in 5s...", exc_info=True)
            await asyncio.sleep(5)

def run_bot(token):
    """Wrapper function to run the async event loop per bot thread."""
    asyncio.run(run_bot_async(token))

# ==========================================
# APPLICATION LIFECYCLE & THREAD SPAWNING
# ==========================================
# Fired when FastAPI starts. Iterates over all configured bot tokens, 
# registers their user IDs, and spawns an independent background daemon thread per bot.
@app.on_event("startup")
def startup_event():
    if not BOT_TOKENS:
        logger.error("No BOT_TOKENS provided in environment variables!")
        return
        
    for token in BOT_TOKENS:
        fetch_bot_user_id(token)
        # Launch each bot in its own isolated background thread with its unique token argument
        thread = threading.Thread(target=run_bot, args=(token,), daemon=True)
        thread.start()

# Standard Kubernetes readiness/liveness health probe endpoint
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "ollama_host": OLLAMA_HOST,
        "tokens_loaded": len(BOT_TOKENS),
        "token_model_mapping": TOKEN_MODEL_MAP,
        "registered_bots": len(BOT_USER_IDS)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
