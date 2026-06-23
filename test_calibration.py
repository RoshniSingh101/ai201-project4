import json
import os
import detector

# Load the env file to ensure GROQ_API_KEY is active
from dotenv import load_dotenv
load_dotenv()

# Define test inputs
tests = [
    {
        "name": "Clearly AI-Generated",
        "text": (
            "Artificial intelligence represents a transformative paradigm shift in modern society. "
            "It is important to note that while the benefits of AI are numerous, it is equally "
            "essential to consider the ethical implications. Furthermore, stakeholders across "
            "various sectors must collaborate to ensure responsible deployment."
        )
    },
    {
        "name": "Clearly Human-Written",
        "text": (
            "ok so i finally tried that new ramen place downtown and honestly? "
            "underwhelming. the broth was fine but they put WAY too much sodium in it and "
            "i was thirsty for like three hours after. my friend got the spicy version and "
            "said it was better. probably won't go back unless someone drags me there"
        )
    },
    {
        "name": "Borderline: Formal Human Writing",
        "text": (
            "The relationship between monetary policy and asset price inflation has been "
            "extensively studied in the literature. Central banks face a fundamental tension "
            "between their mandate for price stability and the unintended consequences of "
            "prolonged low interest rates on equity and real estate valuations."
        )
    },
    {
        "name": "Borderline: Lightly Edited AI Output",
        "text": (
            "I've been thinking a lot about remote work lately. There are genuine tradeoffs — "
            "flexibility and no commute on one side, isolation and blurred work-life boundaries "
            "on the other. Studies show productivity varies widely by individual and role type."
        )
    }
]

def run_calibration():
    print("=" * 60)
    print("PROVENANCE GUARD PIPELINE CALIBRATION TESTING")
    print("=" * 60)
    
    for t in tests:
        name = t["name"]
        text = t["text"]
        
        llm_score, explanation = detector.evaluate_llm_signal(text)
        styl_score = detector.evaluate_stylometric_signal(text)
        verdict, confidence, combined_score = detector.combine_signals(llm_score, styl_score)
        label_info = detector.get_transparency_label(verdict, confidence)
        
        print(f"Sample: {name}")
        print(f"  LLM Score (AI-likeness)     : {llm_score:.4f}")
        print(f"  LLM Explanation             : {explanation}")
        print(f"  Stylometric Score (Uniform)  : {styl_score:.4f}")
        print(f"  Combined AI Score           : {combined_score:.4f}")
        print(f"  Verdict                     : {verdict}")
        print(f"  Calibrated Confidence       : {confidence:.4f}")
        print(f"  Label Header                : {label_info['header']}")
        print(f"  Label Text                  : {label_info['text']}")
        print("-" * 60)

if __name__ == "__main__":
    run_calibration()
