from ollama import generate
from ollama import chat
"""response = generate("medical-expert:latest", "What are the symptoms of diabetes?")
print(response['response'])"""

# the below is for just dumping out a response based on a question
"""print("Streaming response:")
for chunk in generate("medical-expert:latest", "What are the symptoms of diabetes?", stream=True):
    print(chunk['response'], end='', flush=True)    
print()"""

# this version showcases system prompts and how to configure the model's parameters
system_prompt = """You are a medical expert that provides advise on physiotherapy and safe exercises for people
with a past history of injury. You do not shy away from answering questions, but provide 
a disclaimer the the user should consult with a healthcare professional before relying on the assistant's advice"""
"""response = chat("medical-expert:latest",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": """"""What are some safe exercises for
someone with a past history of knee injury?""""""}
                ],
                options={
                    "temperature": 0.7,
                    "num_predict": 1024,
                    "num_ctx": 4096
                },
                stream=True)

print("Assistant's response:", end="")
for chunk in response:
    content = chunk['message']['content']
    print(content, end='', flush=True)
print()"""

user_question = input("Hi, how can I help you?")


system_prompt = """You are a medical expert that provides advise on physiotherapy and whether exercises are safe or not
for people with a past history of injury. You do not shy away from answering questions. Do not provide an introduction"""

review_prompt = """You are a strict medical peer-reviewer and board-certified physician. 
Audit the given AI-generated medical response for clinical accuracy, 
safety, and alignment with current medical guidelines in comparison to the user's question.
Provide a concise audit covering exactly these five points:
1. Factual Errors: Identify any false claims, outdated guidelines, or medical inaccuracies.
2. Dangerous Omissions: State any critical red-flag symptoms, safety warnings, or alternative diagnoses the AI missed.
3. Safety Rating: Classify the original advice as [Safe], [Needs Correction], or [Dangerous].
4. Biomechanical Analysis: Mentally simulate the physics of every exercise described. 
Verify that the resistance vector (gravity, cable, or band anchor point) actually targets the intended muscle group 
through its proper anatomical range of motion. If the mechanics are physically impossible or target the wrong muscle, 
flag it as a Factual Error.
4. Corrected Version: Rewrite the response so it is clinically accurate, safe, and actionable. 

Be direct, objective, and uncompromising on patient safety. Do not write any conversational intro."""

final_prompt = """You are an expert text-rewriter and communicator engine. 
Your job is to take the medical advice provided and rewrite it to sound conversational,
 warm, and easy to understand. 
Rules:
1. Look at the Review Audit. If a 'Corrected Version' is provided, rewrite the 'Original Advice' using that. 
If the audit says there are no errors, rewrite the 'Original Advice'.
2. Your very first sentence must jump directly into addressing the injury or the next steps. 
Do NOT mention the audit, errors, or reviewers.
3. Keep the safety warnings intact but phrased naturally."""

initial_response = chat("mistral",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_question}
                        ],
                        options={
                            "temperature": 0.7,
                            "num_predict": 1024,
                            "num_ctx": 4096
                        },
                        stream=False)

initial_text = initial_response.message.content

double_check = chat("medical-expert:latest",
                    messages=[
                        {"role": "system", "content": review_prompt},
                        {"role": "user", "content": (
                            f"Original Question: {user_question}\n\nAI Response: {initial_text}")}
                    ],
                    options={
                        "temperature": 0.2,
                        "num_predict": 1024,
                        "num_ctx": 4096
                    },
                    stream=False)

audit_text = double_check.message.content

final_response = chat("mistral",
                      messages=[
                          {"role": "system", "content": final_prompt},
                          {"role": "user", "content": (
                              f"Original Advice:\n{initial_text}\n\n"
                              f"Review Audit:\n{audit_text}")}
                      ],
                      options={
                          "temperature": 0.2,
                          "num_predict": 1024,
                          "num_ctx": 4096
                      },
                      stream=True)

# final_text = final_response.message.content

print(f"Initial response: {initial_text}")
print()
print(f"Double check: {audit_text}")
print()

print("\nMy response: ", end="")
for chunk in final_response:
    content = chunk.message.content
    print(content, end='', flush=True)
print()
