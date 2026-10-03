import requests

URL = "http://localhost:11434/api/chat"
MODEL = "qwen3:4b"
TIMEOUT = 500


def chat(messages: list) -> dict | None:
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
    }
    try:
        response = requests.post(URL, json=payload, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.Timeout:
        print("请求超时，请稍后重试。")
    except requests.ConnectionError:
        print("无法连接 Ollama，请确认服务已启动。")
    except requests.HTTPError as error:
        if error.response.status_code == 404:
            print(f"找不到模型 {MODEL}，请检查模型名称或先下载模型。")
        else:
            print(f"请求失败，HTTP 状态码：{error.response.status_code}。")
    except requests.RequestException as error:
        print(f"请求出错：{error}")
    return None

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
        if response is None:
            messages.pop()
            continue

        easy_message = easy_answer(response)
        print("Assistant:", easy_message)
        messages.append({"role": "assistant", "content": easy_message})


if __name__ == "__main__":
    main()
