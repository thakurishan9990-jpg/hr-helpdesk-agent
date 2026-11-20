"""
Command-line chat with the Nimbus HR/IT Helpdesk agent.

Run:  python main.py            (add --debug to see which tools were used)
Type 'exit' to quit.
"""

import sys

from helpdesk.agent import ask


def main():
    debug = "--debug" in sys.argv
    print("Nimbus HR/IT Helpdesk  (type 'exit' to quit)")
    print("Try: 'How many leave days does E102 have left?' or 'What is the WFH policy?'\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in {"exit", "quit", "q"}:
            break
        if not question:
            continue

        try:
            result = ask(question)
        except Exception as e:  # network/API problems shouldn't crash the chat
            print(f"Bot: Sorry, something went wrong ({type(e).__name__}: {e})\n")
            continue

        print(f"Bot: {result['answer']}\n")
        if debug:
            print(f"     tools used : {[t['tool'] for t in result['tool_log']]}")
            print(f"     guardrails : {result['notes']}\n")

    print("Goodbye!")


if __name__ == "__main__":
    main()
