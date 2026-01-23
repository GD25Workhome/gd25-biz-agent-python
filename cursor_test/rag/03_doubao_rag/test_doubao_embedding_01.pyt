from volcenginesdkarkruntime import Ark

client = Ark(
    # 从环境变量中获取您的 API Key。此为默认方式，您可根据需要进行修改
    api_key="5bf7a406-4574-45a9-a8db-c183c63030ac",
)

print("----- multimodal embeddings request -----")
resp = client.multimodal_embeddings.create(
    model="doubao-embedding-vision-250615",
    input=[
        {
            "type":"text",
            "text":"天很蓝，海很深"
        },
        {
            "type": "image_url",
            "image_url": {
                "url": "https://ark-project.tos-cn-beijing.volces.com/images/view.jpeg"
            }
        }
    ]
)
print(resp)