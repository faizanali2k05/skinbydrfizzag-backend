# Updated c:\Users\Faizan\StudioProjects\Skin By Dr. Fizza G\ai_backend\app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return "AI Skin Consultant Backend is Running!"

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message', '')

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    # Get API Key from environment
    api_key = os.environ.get("OPENAI_API_KEY")
    
    # Check if key exists and isn't the placeholder
    if not api_key or "YOUR_OPENAI_API_KEY_HERE" in api_key:
        return jsonify({"error": "OpenAI API Key is missing or invalid in Render Environment Variables."}), 500

    try:
        # Initialize client inside the route to ensure fresh env vars
        client = OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model="gpt-3.5-turbo", # Switched to gpt-3.5-turbo for maximum compatibility
            messages=[
                {"role": "system", "content": "You are a helpful AI skin care consultant for 'Skin By Dr. Fizza G' clinic. Answer questions about skin care, procedures, and clinic services politely."},
                {"role": "user", "content": user_message}
            ]
        )
        ai_message = response.choices[0].message.content
        return jsonify({"response": ai_message})
    except Exception as e:
        print(f"Error: {e}")
        error_msg = str(e)
        if "insufficient_quota" in error_msg:
            return jsonify({"error": "OpenAI API quota exceeded. Please check billing."}), 500
        return jsonify({"error": f"AI Error: {error_msg}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
