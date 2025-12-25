import os
import random
import time
import json
from openai import OpenAI
from colorama import Fore, Style, init

# Initialize Colorama
init(autoreset=True)

# --- CONFIGURATION ---
client = OpenAI()

class ChaosClassroom:
    def __init__(self):
        self.topic = ""
        self.curriculum = [] 
        self.test_questions = [] 
        
        # Student Internal State
        self.knowledge_ledger = []
        self.attention_span = 80 
        self.attempts_left = 3
        self.persona = ""
        
        # CONVERSATION STATE
        self.student_conversation_id = None 
        
        # EVENT FLAGS
        self.is_asleep = False
        self.alien_countdown = -1  # -1 means no alien event
        
    def print_system(self, text):
        print(f"{Fore.CYAN}[SYSTEM]: {text}{Style.RESET_ALL}")

    def print_student(self, text):
        print(f"{Fore.YELLOW}[STUDENT]: {text}{Style.RESET_ALL}")

    def print_event(self, text):
        print(f"{Fore.RED}{Style.BRIGHT}\n>>> RANDOM EVENT: {text} <<<{Style.RESET_ALL}\n")

    def _call_llm(self, input_items, json_mode=False, conversation_id=None):
        """
        Generic wrapper. 
        Removed temperature and top_p to rely on model defaults.
        """
        try:
            response_format = {"type": "text"}
            if json_mode:
                response_format = {"type": "json_object"} 
            
            kwargs = {
                "model": "gpt-5.2",
                "input": input_items,
                "text": {"format": response_format},
                "max_output_tokens": 2048,
            }
            
            # Only pass conversation_id if it exists
            if conversation_id:
                kwargs["conversation"] = conversation_id

            response = client.responses.create(**kwargs)
            return response.output_text
            
        except Exception as e:
            self.print_system(f"API Error: {e}")
            return "{}" if json_mode else "Error"



    def init_student_conversation(self):
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
        
        try:
            conv = client.conversations.create(
                items=[
                    {
                        "type": "message", 
                        "role": "system", 
                        "content": [{"type": "input_text", "text": system_prompt}]
                    }
                ]
            )
            self.student_conversation_id = conv.id
            
        except Exception as e:
            self.print_system(f"Failed to create conversation: {e}")
    # --- SETUP FUNCTIONS (Stateless) ---

    def select_persona(self):
        print(f"\n{Fore.MAGENTA}--- SELECT YOUR STUDENT ---{Style.RESET_ALL}")
        options = [
            "The 'Literalist': Writes down exactly what you say, word for word. If you joke, they treat it as fact. Zero nuance.",
            "The 'Nodder': Understands NOTHING but never asks questions. Just says 'Okay' or 'Got it' to end the conversation.",
            "The 'Try-Hard': Hyper-enthusiastic, constantly flexing irrelevant knowledge, annoying buzzwords.",
            "The 'Rabbit Hole': Constantly asks 'But why?' or 'So what?' about minor details, trying to derail the topic.",
            "The 'Gaslighter': Intentionally misinterprets ambiguous sentences to make you look wrong."
        ]
        for i, p in enumerate(options):
            print(f"{i+1}. {p}")
        print("6. Custom")
        
        choice = input("Select (1-6): ").strip()
        if choice == "6": self.persona = input("Describe the student: ")
        elif choice in ["1", "2", "3", "4", "5"]: self.persona = options[int(choice)-1]
        else: self.persona = options[0]

    def set_curriculum(self):
        self.topic = input("Enter the topic you want to teach: ")
        self.print_system("Generating Curriculum...")
        
        items = [
            {"role": "system", "content": [{"type": "input_text", "text": "Curriculum Generator."}]},
            {"role": "user", "content": [{"type": "input_text", "text": f"List 5 simple atomic facts about {self.topic}."}]}
        ]
        # Removed temperature arg
        raw = self._call_llm(items)
        self.curriculum = [l.strip() for l in raw.split('\n') if l.strip()][:5]

        print(f"\n{Fore.MAGENTA}--- CURRICULUM GENERATED ---{Style.RESET_ALL}")
        for fact in self.curriculum:
            print(fact)
        print("-" * 30)

    def generate_test_bank(self):
        self.print_system("Generating Exam Questions...")
        prompt = f"""
        Topic: {self.topic}
        Curriculum: {json.dumps(self.curriculum)}
        Generate 10 open-ended test questions.
        Output JSON: {{ "questions": [ {{ "difficulty": "...", "question": "...", "std_answer": "..." }} ] }}
        """
        items = [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}]
        # Removed temperature arg
        json_str = self._call_llm(items, json_mode=True)
        try:
            data = json.loads(json_str)
            self.test_questions = data.get("questions", [])
        except: self.test_questions = []

    # --- GAMEPLAY FUNCTIONS ---

    def trigger_random_event(self):
        if self.is_asleep or self.alien_countdown >= 0: return 
        if random.random() > 0.3: return 
        
        events = ["NAP", "MISCONCEPTION", "ALIEN", "FIRE_DRILL", "EUREKA"]
        weights = [0.25, 0.30, 0.10, 0.20, 0.15]
        event = random.choices(events, weights)[0]
        
        if event == "NAP":
            self.is_asleep = True
            self.print_event("The student just faceplanted. They are ASLEEP.")
            
        elif event == "MISCONCEPTION":
            if not self.knowledge_ledger: return
            idx = random.randint(0, len(self.knowledge_ledger)-1)
            prompt = f"Rewrite this to be WRONG: '{self.knowledge_ledger[idx]}'"
            bad_note = self._call_llm([{"role": "user", "content": [{"type": "input_text", "text": prompt}]}])
            self.knowledge_ledger[idx] = bad_note
            self.print_event("The student looks confused... (Memory corrupted!)")
            
        elif event == "ALIEN":
            self.alien_countdown = 3
            self.attempts_left = 1 
            self.print_event("ALIEN INVASION! 👽 Pass the TEST in 3 turns or Earth dies.")
            
        elif event == "FIRE_DRILL":
            self.print_event("FIRE DRILL! 🔥 Fortunately I'm too lazy to implement a fire drill so the fire fades away naturally.")
            # if len(self.knowledge_ledger) > 0:
            #     self.knowledge_ledger = self.knowledge_ledger[:-2]
            #     self.print_event(f"FIRE DRILL! 🔥 Notes lost.")
                
        elif event == "EUREKA":
            if len(self.knowledge_ledger) >= 2:
                prompt = f"Synthesize these notes: {self.knowledge_ledger}"
                good_note = self._call_llm([{"role": "user", "content": [{"type": "input_text", "text": prompt}]}])
                self.knowledge_ledger.append(good_note)
                self.print_event("EUREKA! 💡 The student connected the dots.")

    def process_learning(self, teacher_input_items):
        # 1. Extract text for mechanics
        text_content = " ".join([item["text"] for item in teacher_input_items if item["type"] == "input_text"]).upper()
        
        # Check Wake Up Status
        if self.is_asleep:
            if any(w in text_content for w in ["WAKE", "UP", "HEY"]):
                self.is_asleep = False
                self.attention_span = 50
                self.print_system("The student wakes up, groggy.")
                return None
            else:
                return "ASLEEP"

        # Mechanics: Word Count & Questions
        word_count = len(text_content.split())
        if word_count > 35:
            self.attention_span -= 15
            self.print_system(f"Message too long! Attention dropped to {self.attention_span}%.")
        if "?" in text_content:
            self.attention_span = min(100, self.attention_span + 10)

        # Fail state: Attention too low
        if self.attention_span < 20: 
            return None

        # 2. Prepare the "Notebook Context"
        # We show the student what they have written so far.
        notebook_context = "\n".join([f"- {note}" for note in self.knowledge_ledger]) if self.knowledge_ledger else "(Notebook is empty)"

        prompt = f"""
        You are the internal brain of a student taking notes. 
        Persona: {self.persona}.
        Current Attention: {self.attention_span}%.
        
        YOUR CURRENT NOTEBOOK:
        {notebook_context}
        
        TEACHER'S INPUT:
        (See user message below)
        
        TASK:
        Write the NEXT LINE for your notebook based on the teacher's input.
        
        RULES:
        - Take notes ONLY on what the teacher JUST SAID. DO NOT use outside knowledge.
        - Take into account your ATTENTION SPAN:
        - If attention < 40%, you may be confused and write a confused note.
        - Notes should follow your persona style.
        - If the teacher is correcting a previous fact, write a note like: "Correction: [Old Fact] is actually [New Fact]."
        - If the teacher is adding new info, just write the fact.
        - If you are confused (low attention), write a confused note.
        - DO NOT use outside knowledge. Only write what the teacher just said.
        - Return ONLY the short note string.
        """
        
        items = [
            {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
            {"role": "user", "content": teacher_input_items}
        ]
        
        # Stateless call (the "brain" processing the input)
        note = self._call_llm(items)
        
        if "NOTHING" in note or len(note) < 3: 
            return None
            
        return note

    def chat_with_student(self, teacher_input_items, new_knowledge_note):
        if not self.student_conversation_id:
            self.init_student_conversation()

        if new_knowledge_note == "ASLEEP":
            return "Zzzzz... (snore)..."

        # We construct the "Knowledge Cage"
        # We feed the student their own notes so they know exactly what they "know" vs "don't know"
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
        
        turn_items = [
            {"role": "system", "content": [{"type": "input_text", "text": state_msg}]},
            {"role": "user", "content": teacher_input_items}
        ]
        
        response_text = self._call_llm(
            turn_items, 
            conversation_id=self.student_conversation_id
        )
        
        return response_text

    def run_quiz(self):
        self.attempts_left -= 1
        self.print_system("\n--- FINAL EXAM INITIATED ---")
        score = 0
        quiz_subset = random.sample(self.test_questions, min(6, len(self.test_questions)))
        
        full_brain_dump = "\n".join(self.knowledge_ledger)
        self.print_system(f"[DEBUG] Student's Brain Dump:\n{full_brain_dump}\n")
        
        for q in quiz_subset:
            print(f"\n{Fore.WHITE}Q: {q['question']}{Style.RESET_ALL}")
            
            items = [
                {"role": "system", "content": [{"type": "input_text", "text": f"Answer based ONLY on these notes:\n{full_brain_dump}\nIf unknown, admit it."}]},
                {"role": "user", "content": [{"type": "input_text", "text": q['question']}]}
            ]
            # Removed temperature arg
            student_ans = self._call_llm(items)
            self.print_student(f"Answer: {student_ans}")
            
            grade_items = [
                {"role": "system", "content": [{"type": "input_text", "text": "You are a teacher grading a test."}]},
                {"role": "user", "content": [{"type": "input_text", "text": f"Q: {q['question']}\nStd Answer: {q['std_answer']}\nStudent Ans: {student_ans}\nPass/Fail?"}]}
            ]
            # Removed temperature arg
            grade = self._call_llm(grade_items)
            
            if "PASS" in grade.upper():
                print(f"{Fore.GREEN}>> CORRECT{Style.RESET_ALL}")
                score += 1
            else:
                print(f"{Fore.RED}>> INCORRECT{Style.RESET_ALL}")
            time.sleep(1)

        if score >= (len(quiz_subset) - 1):
            self.print_system(f"🎉 PASSED! You taught them well.")
            return True
        else:
            self.print_system(f"❌ FAILED. Attempts left: {self.attempts_left}")
            return False

    def start(self):
        print(f"{Fore.MAGENTA}Welcome to CHAOS CLASSROOM v7.1 (No Temp/TopP){Style.RESET_ALL}")
        
        self.select_persona()
        self.set_curriculum()
        self.generate_test_bank()
        self.init_student_conversation()
        
        print("\n" + "="*40)
        print(f"TOPIC: {self.topic}")
        print("COMMANDS: /image <url>, TEST, QUIT")
        
        while self.attempts_left > 0:
            if self.alien_countdown >= 0:
                print(f"{Fore.RED}ALIEN DEADLINE: {self.alien_countdown} TURNS{Style.RESET_ALL}")
                self.alien_countdown -= 1
                if self.alien_countdown == 0:
                    print(f"{Fore.RED}EARTH DESTROYED.{Style.RESET_ALL}")
                    break

            raw_input = input(f"\n{Fore.GREEN}You: {Style.RESET_ALL}").strip()
            if raw_input.upper() == "QUIT": break
            if raw_input.upper() == "TEST":
                if self.run_quiz(): break
                continue

            input_items = []
            if raw_input.startswith("/image"):
                parts = raw_input.split(" ", 1)
                if len(parts) > 1:
                    input_items.append({"type": "image_url", "image_url": {"url": parts[1]}})
                    self.print_system(f"Attached image...")
                else:
                    self.print_system("Missing URL.")
                    continue
            else:
                input_items.append({"type": "input_text", "text": raw_input})

            self.trigger_random_event()

            new_note = self.process_learning(input_items)
            if new_note and new_note != "ASLEEP":
                self.knowledge_ledger.append(new_note)

            response = self.chat_with_student(input_items, new_note)
            self.print_student(response)

if __name__ == "__main__":
    game = ChaosClassroom()
    game.start()