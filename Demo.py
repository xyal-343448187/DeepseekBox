import requests
import json

if __name__ == '__main__':
    # url = "https://api.modelarts-maas.com/v1/chat/completions"
    url = "https://maas-cn-southwest-2.modelarts-maas.com/v1/infers/8a062fd4-7367-4ab4-a936-5eeb8fb821c4/v1/chat/completions",
    api_key = "test"    # Send request.
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }
    data = {
        "model": "DeepSeek-R1",  # 调用时的模型名称。
        "max_tokens": 1024,  # 最大输出token数。
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "你好"}
        ],
        # 是否开启流式推理，默认为False,表示不开启流式推理。
        "stream": True,
        # 在流式输出时是否展示使用的token数目。只有当stream为True时该参数才会生效。
        # "stream_options": {"include_usage": True},
        # 控制采样随机性的浮点数，值较低时模型更具确定性，值较高时模型更具创造性。"0"表示贪婪取样。默认为0.6。
        "temperature": 0.6
    }
    response = requests.post(url, headers=headers, data=json.dumps(data), verify=False)
    print(response.status_code)
    print(response.text)