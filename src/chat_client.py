import requests

URL = "http://localhost:11434/api/chat"
MODEL = "qwen3:4b"
TIMEOUT = 500


def chat(messages: list) -> dict:
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
    }
    response = requests.post(f"{URL}", json=payload, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()

#简化回答，而不是把思考和推理部分都讲出来
def easy_answer(response) -> str:
    
    message = response["message"]["content"]
    if "</think>" in response["message"]["content"]:
       
        _, easy_message = message.split("</think>",1)# 只保留回答部分
        return easy_message.strip()    
    return message
def main():
    messages = []
    while True:
        prompt = input("You (type 'exit' to quit): ").strip()
        if prompt.lower() == "exit":
            break
        if not prompt:
            continue

        messages.append({"role": "user", "content": prompt})
        response = chat(messages)
        easy_message = easy_answer(response)
        print("Assistant:", easy_message)
        messages.append({"role": "assistant", "content": easy_message})


if __name__ == "__main__":
    main()
