from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os
import requests
import uuid
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Initialize Clients
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") # Use Service Role Key for backend
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID") # The UUID of Dr. Fizza's profile

openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

@app.route('/')
def home():
    return "Skin By Dr. Fizza G - Integrated Backend is Running!"

# --- WHATSAPP WEBHOOK ---

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """Meta Webhook Verification"""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode == 'subscribe' and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Handle incoming WhatsApp messages"""
    data = request.json
    
    # Check if it's a message event
    if data.get('object') == 'whatsapp_business_account':
        for entry in data.get('entry', []):
            for change in entry.get('changes', []):
                value = change.get('value', {})
                if 'messages' in value:
                    for message in value['messages']:
                        sender_phone = message.get('from')
                        message_body = message.get('text', {}).get('body', '')
                        wa_message_id = message.get('id')
                        
                        if message_body:
                            process_incoming_wa_message(sender_phone, message_body, wa_message_id)
        
        return jsonify({"status": "received"}), 200
    
    return jsonify({"error": "Invalid object"}), 400

def process_incoming_wa_message(phone, text, wa_id):
    """Business logic for incoming WhatsApp messages"""
    try:
        # 1. Find or create user profile
        user_res = supabase.table('profiles').select('*').eq('phone', phone).execute()
        
        if not user_res.data:
            # Create a new profile for the WhatsApp user
            new_user_id = str(uuid.uuid4())
            new_user = {
                "id": new_user_id,
                "full_name": f"WA User {phone}",
                "phone": phone,
                "role": "user",
                "status": "active"
            }
            supabase.table('profiles').insert(new_user).execute()
            user_id = new_user_id
        else:
            user_id = user_res.data[0]['id']

        # 2. Find or create conversation
        conv_res = supabase.table('conversations').select('*').eq('user_id', user_id).execute()
        
        if not conv_res.data:
            # Create new conversation with admin
            if not ADMIN_ID:
                print("Error: ADMIN_ID not set in environment variables.")
                return

            conv_data = {
                "user_id": user_id,
                "admin_id": ADMIN_ID,
                "last_message": text,
                "unread_count": 1,
                "platform": "whatsapp",
            }
            new_conv = supabase.table('conversations').insert(conv_data).execute()
            conversation_id = new_conv.data[0]['id']
        else:
            conversation_id = conv_res.data[0]['id']

        # 3. Store message
        msg_data = {
            "conversation_id": conversation_id,
            "sender_id": user_id,
            "sender_role": "user",
            "text": text,
            "platform": "whatsapp",
            "whatsapp_message_id": wa_id
        }
        supabase.table('messages').insert(msg_data).execute()
        
    except Exception as e:
        print(f"Error processing WA message: {e}")

# --- ADMIN API (Used by Flutter) ---

@app.route('/send-message', methods=['POST'])
def send_message():
    """Endpoint for Admin to send a message to WhatsApp"""
    data = request.json
    conversation_id = data.get('conversation_id')
    message_text = data.get('message')
    recipient_phone = data.get('phone')
    
    if not all([conversation_id, message_text, recipient_phone]):
        return jsonify({"error": "Missing parameters"}), 400

    try:
        # 1. Send via WhatsApp API
        url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient_phone,
            "type": "text",
            "text": {"body": message_text}
        }
        
        response = requests.post(url, headers=headers, json=payload)
        res_data = response.json()
        
        if response.status_code == 200:
            wa_id = res_data.get('messages', [{}])[0].get('id')
            
            # 2. Store in Supabase
            msg_data = {
                "conversation_id": conversation_id,
                "sender_id": ADMIN_ID,
                "sender_role": "admin",
                "text": message_text,
                "platform": "whatsapp",
                "whatsapp_message_id": wa_id
            }
            supabase.table('messages').insert(msg_data).execute()
            
            return jsonify({"status": "success", "wa_id": wa_id})
        else:
            return jsonify({"error": "WhatsApp API error", "details": res_data}), response.status_code
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- AI CONSULTANT ROUTE ---

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message', '')
    user_id = data.get('user_id') # Optional: for server-side persistence

    if not openai_client or not user_message:
        return jsonify({"error": "OpenAI not configured or no message"}), 400

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful AI skin care consultant for 'Skin By Dr. Fizza G' clinic. Keep responses helpful and concise.",
                },
                {"role": "user", "content": user_message},
            ],
        )
        ai_message = response.choices[0].message.content
        
        # Note: If user_id is provided, we could store it here using SUPABASE_KEY (Service Role)
        # However, Flutter is currently handling storage. 
        # For WhatsApp AI, we would definitely store it here.
        
        return jsonify({"response": ai_message})
    except Exception as e:
        print(f"AI Chat Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Use PORT from environment (required for Render)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
