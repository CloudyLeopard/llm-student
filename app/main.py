import asyncio
import json
import random
import os
from fastapi import FastAPI, WebSocket, Request, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from openai import OpenAI

# --- CONFIGURATION ---
# We use standard ANSI codes for the web terminal
RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
WHITE = "\033[37m"

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")
client = OpenAI()

@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    game = AsyncTeachingSimulator(websocket)
    try:
        await game.start()
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        await websocket.send_text(f"{RED}Error: {e}{RESET}\r\n")
        await websocket.close()

# --- THE GAME LOGIC (Exact Port) ---

class AsyncTeachingSimulator:
    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.topic = ""
        self.curriculum = [] 
        self.test_questions = [] 
        
        # Student Internal State
        self.knowledge_ledger = []
        self.attention_span = 80 
        self.attempts_left = 3
        self.persona = ""
        
        # CONVERSATION STATE
        self.conversation_history = [] # Replacing specific conversation_id with manual history for standard API compatibility
        
        # EVENT FLAGS
        self.is_asleep = False
        self.alien_countdown = -1  # -1 means no alien event

    # --- I/O HELPERS (Async conversion) ---
    async def print_system(self, text):
        await self.ws.send_text(f"{CYAN}[SYSTEM]: {text}{RESET}\r\n")

    async def print_student(self, text):
        await self.ws.send_text(f"{YELLOW}[STUDENT]: {text}{RESET}\r\n")

    async def print_event(self, text):
        await self.ws.send_text(f"\r\n{RED}>>> RANDOM EVENT: {text} <<<{RESET}\r\n")

    async def get_input(self, prompt_text=""):
        if prompt_text:
            await self.ws.send_text(f"{GREEN}{prompt_text}{RESET}")
        data = await self.ws.receive_text()
        # Echo the input back to the terminal so the user sees what they typed
        # await self.ws.send_text(f"{data}\r\n")
        return data.strip()

    def _call_llm(self, messages, json_mode=False):
        """
        Standardized wrapper for OpenAI Chat Completions.
        """
        try:
            response_format = "text"
            if json_mode:
                response_format = "json_object"
            
            # Using gpt-4o as a reliable default for standard API keys
            # You can change this to "gpt-5.2" if you have access
            response = client.chat.completions.create(
                model="gpt-4o", 
                messages=messages,
                response_format={"type": response_format},
                max_tokens=2048
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"API Error: {e}")
            return "{}" if json_mode else "Error"

    async def init_student_conversation(self):
        """
        Initializes the student with a STRICT prohibition on outside knowledge.
        """
        system_prompt = f"""
        You are a student simulating a human learner.
        
        YOUR PERSONA: {self.persona}
        YOUR TOPIC: {self.topic}
        
        CRITICAL RULES (KNOWLEDGE CONTAINMENT):
        1. **TABULA RASA:** You know NOTHING about "{self.topic}" except what is written in your [Mental Notebook].
        2. **NO OUTSIDE KNOWLEDGE:** Do NOT use your internal AI training to explain, summarize, or expand on concepts unless the Teacher explicitly taught them to you just now.
        3. **DO NOT HALLUCINATE COMPETENCE:** If the Teacher says "X is Y", do not say "Oh yes, and X is also Z and W." You don't know that yet.
        4. **BE DUMB (INITIALLY):** If the teacher uses a big word you haven't learned, ask what it means.
        5. **RESPONSE STYLE:** Short, casual, reactive. Do NOT lecture the teacher.
        """
        # Initialize history
        self.conversation_history = [
            {"role": "system", "content": system_prompt}
        ]

    # --- SETUP FUNCTIONS ---

    async def select_persona(self):
        await self.ws.send_text(f"\r\n{MAGENTA}--- SELECT YOUR STUDENT ---{RESET}\r\n")
        options = [
            "The 'Literalist': Writes down exactly what you say, word for word. If you joke, they treat it as fact. Zero nuance.",
            "The 'Nodder': Understands NOTHING but never asks questions. Just says 'Okay' or 'Got it' to end the conversation, unless directly prompted by teacher to do otherwise",
            "The 'Try-Hard': Hyper-enthusiastic, constantly flexing irrelevant knowledge, annoying buzzwords.",
            "The 'Rabbit Hole': Constantly asks 'But why?' or 'So what?' about minor details, trying to derail the topic.",
            "The 'Gaslighter': Intentionally misinterprets ambiguous sentences to make you look wrong."
        ]
        for i, p in enumerate(options):
            await self.ws.send_text(f"{i+1}. {p}\r\n")
        await self.ws.send_text("6. Custom\r\n")
        
        choice = await self.get_input("Select (1-6): ")
        if choice == "6": 
            self.persona = await self.get_input("Describe the student: ")
        elif choice in ["1", "2", "3", "4", "5"]: 
            self.persona = options[int(choice)-1]
        else: 
            self.persona = options[0]

    async def set_curriculum(self):
        self.topic = await self.get_input("Enter the topic you want to teach: ")
        await self.print_system("Generating Curriculum...")
        
        messages = [
            {"role": "system", "content": "Curriculum Generator."},
            {"role": "user", "content": f"List 5 simple atomic facts about {self.topic}."}
        ]
        raw = self._call_llm(messages)
        self.curriculum = [l.strip() for l in raw.split('\n') if l.strip()][:5]

        # # Print curriculum to terminal
        # await self.ws.send_text(f"\r\n{MAGENTA}--- CURRICULUM GENERATED ---{RESET}\r\n")
        # for fact in self.curriculum:
        #     await self.ws.send_text(f"{fact}\r\n")
        # await self.ws.send_text("-" * 30 + "\r\n")

    async def generate_test_bank(self):
        await self.print_system("Generating Exam Questions...")
        prompt = f"""
        Topic: {self.topic}
        Curriculum: {json.dumps(self.curriculum)}
        Generate 10 open-ended test questions.
        Output JSON: {{ "questions": [ {{ "difficulty": "...", "question": "...", "std_answer": "..." }} ] }}
        """
        messages = [{"role": "user", "content": prompt}]
        json_str = self._call_llm(messages, json_mode=True)
        try:
            data = json.loads(json_str)
            self.test_questions = data.get("questions", [])
        except: 
            self.test_questions = []

    # --- GAMEPLAY FUNCTIONS ---

    async def trigger_random_event(self):
        if self.is_asleep or self.alien_countdown >= 0: return 
        if random.random() > 0.3: return 
        
        events = ["NAP", "MISCONCEPTION", "ALIEN", "FIRE_DRILL", "EUREKA"]
        weights = [0.25, 0.30, 0.10, 0.20, 0.15]
        event = random.choices(events, weights)[0]
        
        if event == "NAP":
            self.is_asleep = True
            await self.print_event("The student just faceplanted. They are ASLEEP.")
            
        elif event == "MISCONCEPTION":
            if not self.knowledge_ledger: return
            idx = random.randint(0, len(self.knowledge_ledger)-1)
            prompt = f"Rewrite this to be WRONG: '{self.knowledge_ledger[idx]}'"
            bad_note = self._call_llm([{"role": "user", "content": prompt}])
            self.knowledge_ledger[idx] = bad_note
            await self.print_event("The student looks confused... (Memory corrupted!)")
            
        elif event == "ALIEN":
            self.alien_countdown = 3
            self.attempts_left = 1 
            await self.print_event("ALIEN INVASION! 👽 Pass the TEST in 3 turns or Earth dies.")
            
        elif event == "FIRE_DRILL":
            await self.print_event("FIRE DRILL! 🔥 Fortunately I'm too lazy to implement a fire drill so the fire fades away naturally.")
                
        elif event == "EUREKA":
            if len(self.knowledge_ledger) >= 2:
                prompt = f"Synthesize these notes: {self.knowledge_ledger}"
                good_note = self._call_llm([{"role": "user", "content": prompt}])
                self.knowledge_ledger.append(good_note)
                await self.print_event("EUREKA! 💡 The student connected the dots.")

    async def process_learning(self, teacher_input_text):
        # 1. Mechanics
        text_content = teacher_input_text.upper()
        
        # Check Wake Up Status
        if self.is_asleep:
            if any(w in text_content for w in ["WAKE", "UP", "HEY"]):
                self.is_asleep = False
                self.attention_span = 50
                await self.print_system("The student wakes up, groggy.")
                return None
            else:
                return "ASLEEP"

        # Mechanics: Word Count & Questions
        word_count = len(text_content.split())
        if word_count > 35:
            self.attention_span -= 15
            await self.print_system(f"Message too long! Attention dropped to {self.attention_span}%.")
        if "?" in text_content:
            self.attention_span = min(100, self.attention_span + 10)

        # Fail state: Attention too low
        if self.attention_span < 20: 
            return None

        # 2. Prepare the "Notebook Context"
        notebook_context = "\n".join([f"- {note}" for note in self.knowledge_ledger]) if self.knowledge_ledger else "(Notebook is empty)"

        prompt = f"""
        You are the internal brain of a student taking notes. 
        Persona: {self.persona}.
        Current Attention: {self.attention_span}%.
        
        YOUR CURRENT NOTEBOOK:
        {notebook_context}
        
        TEACHER'S INPUT:
        {teacher_input_text}
        
        TASK:
        Write the NEXT LINE for your notebook based on the teacher's input.
        
        RULES:
        - Always follow your persona. 
            - Your note should follow your persona's style
            - Your understanding may be limited based on your persona.
            - If you are not supposed to understand, write a confused note or even write incorrect information on purpose.
        - Take notes ONLY on what the teacher JUST SAID. DO NOT use outside knowledge.
        - Take into account your ATTENTION SPAN:
        - If attention < 40%, you may be confused and write a confused note.
        - If the teacher is correcting a previous fact, write a note like: "Correction: [Old Fact] is actually [New Fact]."
        - If the teacher is adding new info, just write the fact.
        - If you are confused (low attention), write a confused note.
        - DO NOT use outside knowledge. Only write what the teacher just said.
        - Return ONLY the short note string.
        """
        
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": teacher_input_text}
        ]
        
        # Stateless call (the "brain" processing the input)
        note = self._call_llm(messages)
        
        if "NOTHING" in note or len(note) < 3: 
            return None
            
        return note

    async def chat_with_student(self, teacher_input_text, new_knowledge_note):
        if not self.conversation_history:
            await self.init_student_conversation()

        if new_knowledge_note == "ASLEEP":
            return "Zzzzz... (snore)..."

        current_knowledge = "\n".join(self.knowledge_ledger) if self.knowledge_ledger else "(Notebook is empty)"
        
        state_msg = f"""
        [INTERNAL STATE]
        Attention Span: {self.attention_span}%
        
        [MENTAL NOTEBOOK - THIS IS ALL YOU KNOW]
        {current_knowledge}
        
        [JUST LEARNED]
        You just wrote down: "{new_knowledge_note}"
        
        [INSTRUCTION]
        Reply to the teacher's last message.
        - If the teacher mentioned something NOT in your [Mental Notebook], you represent a student who does NOT understand it yet.
        - Do NOT explain the concept back to the teacher like an expert.
        - React naturally (e.g., "Oh okay," "Wait, what does emergent mean?", "Cool.")
        """
        
        # Add system instruction for this specific turn state
        turn_messages = self.conversation_history + [
            {"role": "system", "content": state_msg},
            {"role": "user", "content": teacher_input_text}
        ]
        
        response_text = self._call_llm(turn_messages)
        
        # Update history (keep it simple for now, append user/assistant)
        self.conversation_history.append({"role": "user", "content": teacher_input_text})
        self.conversation_history.append({"role": "assistant", "content": response_text})
        
        return response_text

    async def run_quiz(self):
        self.attempts_left -= 1
        await self.print_system("\r\n--- FINAL EXAM INITIATED ---")
        score = 0
        quiz_subset = random.sample(self.test_questions, min(6, len(self.test_questions)))
        
        full_brain_dump = "\n".join(self.knowledge_ledger)
        await self.print_system(f"[INFO] Student's Brain Dump:\n{full_brain_dump}\n")
        
        for q in quiz_subset:
            await self.ws.send_text(f"\r\n{WHITE}Q: {q['question']}{RESET}\r\n")
            
            # --- FIXED PROMPT BELOW ---
            # We aggressively constrain the model to ONLY use the provided text.
            student_system_prompt = f"""
            You are a student taking a test.
            
            CRITICAL RULE: You have TOTAL AMNESIA. You have NO knowledge of the world except for the text in your [NOTES] below.
            You should also answer questions in accordance with your persona

            [NOTES]
            {full_brain_dump}

            [PERSONA]
            {self.persona}
            
            INSTRUCTIONS:
            1. Answer the question using ONLY the [NOTES] above.
            2. Write in the style of your persona.
            3. If the answer is not explicitly in the [NOTES], you MUST say "I don't know" or "My notes don't say."
            4. Do NOT use your internal AI training to answer.
            5. If your notes contain typos (e.g., "chatget"), your answer must use those typos. Do not correct them.
            6. Keep your answers short and unsure - you are a student, not an expert.
            """
            
            messages = [
                {"role": "system", "content": student_system_prompt},
                {"role": "user", "content": q['question']}
            ]
            student_ans = self._call_llm(messages)
            await self.print_student(f"Answer: {student_ans}")
            
            # The Teacher AI grades it
            grade_messages = [
                {"role": "system", "content": "You are a strict teacher grading a test."},
                {"role": "user", "content": f"Q: {q['question']}\nStandard Answer: {q['std_answer']}\nStudent Answer: {student_ans}\n\nTask: Grade this. If the student admits they don't know, or answers incorrectly/vaguely compared to the Standard Answer, it is a FAIL.\nOutput: PASS or FAIL."}
            ]
            grade = self._call_llm(grade_messages)
            
            if "PASS" in grade.upper():
                await self.ws.send_text(f"{GREEN}>> CORRECT{RESET}\r\n")
                score += 1
            else:
                await self.ws.send_text(f"{RED}>> INCORRECT{RESET}\r\n")
            
            await asyncio.sleep(1)

        if score >= (len(quiz_subset) - 1):
            await self.print_system(f"🎉 PASSED! You taught them well.")
            return True
        else:
            await self.print_system(f"❌ FAILED. Attempts left: {self.attempts_left}")
            return False

    async def start(self):
        await self.ws.send_text(f"{MAGENTA}Welcome to CHAOS CLASSROOM v8.0 (Web Edition){RESET}\r\n")
        
        await self.select_persona()
        await self.set_curriculum()
        await self.generate_test_bank()
        await self.init_student_conversation()
        
        await self.ws.send_text("\r\n" + "="*40 + "\r\n")
        await self.ws.send_text(f"TOPIC: {self.topic}\r\n")
        await self.ws.send_text("COMMANDS: /image <url>, TEST, QUIT\r\n")
        
        while self.attempts_left > 0:
            # Alien Event Logic
            if self.alien_countdown >= 0:
                await self.ws.send_text(f"{RED}ALIEN DEADLINE: {self.alien_countdown} TURNS{RESET}\r\n")
                self.alien_countdown -= 1
                if self.alien_countdown == 0:
                    await self.ws.send_text(f"{RED}EARTH DESTROYED.{RESET}\r\n")
                    break

            raw_input = await self.get_input(f"\r\n{GREEN}You: {RESET}")
            
            if raw_input.upper() == "QUIT": 
                break
            
            if raw_input.upper() == "TEST":
                if await self.run_quiz(): 
                    break
                continue

            input_text = raw_input
            if raw_input.startswith("/image"):
                # Simplified image handling for text terminal
                parts = raw_input.split(" ", 1)
                if len(parts) > 1:
                    await self.print_system(f"Attached image {parts[1]} (Simulated)")
                    input_text = f"[Image attached: {parts[1]}]"
                else:
                    await self.print_system("Missing URL.")
                    continue

            # Event triggers BEFORE processing
            await self.trigger_random_event()

            new_note = await self.process_learning(input_text)
            
            if new_note and new_note != "ASLEEP":
                self.knowledge_ledger.append(new_note)

            response = await self.chat_with_student(input_text, new_note)
            await self.print_student(response)
        
        await self.ws.send_text(f"\r\n{MAGENTA}GAME OVER. REFRESH TO RESTART.{RESET}\r\n")