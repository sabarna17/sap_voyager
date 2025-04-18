from langchain_openai import AzureChatOpenAI
model = AzureChatOpenAI(
    azure_endpoint=os.getenv('azure_endpoint'),
    openai_api_version=os.getenv('openai_api_version'),
    openai_api_key=os.getenv('openai_api_key'),
    deployment_name=os.getenv('deployment_name_4o'),
    max_tokens=2000,
    max_retries=2,
    temperature=0

def convert_ask_into_steps(ask):
    tool_list = ''
    step = 1
    for tool in sap_tools: 
        tool_list = str(step) + tool_list + tool.name + ', ' + 'value : ' + '\n'
        
    prompt = f"""
    Given a user's free text input related to SAP GUI automation, 
    please analyze the content and creat execution plan without any feedback and codes and
    by using the available tools and create a plan to execute the tools in proper manor.
    
    {tool_list}
    
    User Input - {ask}
    
    """
    # model.invoke({"messages": [("user", ask)]})
    mes = [
                {
                    "role": "system",
                    "content": "You are a helpful assistant to analyse images.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt}
                    ],
                },
            ]    
    
    result = model.invoke(mes)
    result = result.content + '\n\nNote - This is Guidance. Do not blindly follow these instructions. Feel free to fetch the execution result and pivote the plan.'
    return result
