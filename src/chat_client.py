import requests

URL = "http://localhost:11434/api/chat"
MODEL = "qwen3:4b"
TIMEOUT = 500


def chat(prompt:str) -> dict:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "think": False,
    }
    response = requests.post(f"{URL}", json=payload, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()

#简化回答，而不是把思考和推理部分讲出来
def easy_answer(response) -> str:
    
    message = response["message"]["content"]
    if "</think>" in response["message"]["content"]:
       
        _, easy_message = message.split("</think>",1)# 只保留回答部分
        return easy_message.strip()    
    return message
def main():
    prompt = input("Enter your prompt: ")
    response = chat(prompt)
    easy_message = easy_answer(response)
    print("content:", easy_message)
if __name__ == "__main__":
    main()