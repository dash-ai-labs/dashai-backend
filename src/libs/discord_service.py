def send_discord_message(message: str, channel: str):
    import requests
    import json

    # Prepare the payload for Discord webhook
    payload = {"content": message}

    # Send the POST request to the webhook URL
    try:
        response = requests.post(
            channel, data=json.dumps(payload), headers={"Content-Type": "application/json"}
        )

        # Check if the request was successful
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error sending Discord message: {e}")
        return False
