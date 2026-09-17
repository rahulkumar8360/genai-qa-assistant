# Terminal front end.
#
#   python cli.py                          chat about data/docs
#   python cli.py "How long must passwords be?"      ask once and exit
#   python cli.py --docs path\to\folder    chat about your own documents
#   python cli.py --backend offline        force the no-key backend
#
# Inside the chat: /sources shows the passages behind the last answer,
# /reset forgets the conversation, /quit leaves.

import argparse
import textwrap

import config
from qa.assistant import Assistant, KnowledgeBase
from qa.llm import LLMError, make_backend
from qa.prompts import PROMPTS


def print_answer(result):
    print()
    print(textwrap.fill(result["answer"], width=90))
    if result["citations"]:
        print()
        for c in result["citations"]:
            where = c["source"] + (" > " + c["section"] if c["section"] else "")
            print("  [%d] %s" % (c["n"], where))
    print()


def print_sources(result):
    if not result:
        print("Ask a question first.")
        return
    for r in result["retrieved"]:
        print("\n[%d] %s > %s  (score %.2f)" % (r["n"], r["source"], r["section"], r["score"]))
        print(textwrap.indent(textwrap.fill(r["text"], width=86), "    "))
    print()


def main():
    parser = argparse.ArgumentParser(description="Ask questions about a folder of documents")
    parser.add_argument("question", nargs="?", help="ask one question and exit")
    parser.add_argument("--docs", default=config.DOCS_DIR, help="folder of .txt/.md/.pdf files")
    parser.add_argument("--backend", default=None, choices=["auto", "claude", "offline"])
    parser.add_argument("--prompt", default=None, choices=sorted(PROMPTS), help="prompt version")
    args = parser.parse_args()

    kb = KnowledgeBase()
    kb.load_folder(args.docs)
    if not kb.chunks:
        raise SystemExit("No .txt, .md or .pdf files found in %s" % args.docs)

    assistant = Assistant(kb, backend=make_backend(args.backend), prompt_version=args.prompt)

    if args.question:
        try:
            print_answer(assistant.ask(args.question))
        except LLMError as e:
            raise SystemExit(str(e))
        return

    print("Loaded %d documents (%d passages). Backend: %s, prompt %s." % (
        len(kb.docs), len(kb.chunks), assistant.backend.name, assistant.prompt_version))
    if assistant.backend.name == "offline":
        print("Offline mode quotes matching sentences; set ANTHROPIC_API_KEY for real answers.")
    print("Commands: /sources  /reset  /quit\n")

    history = []
    last = None
    while True:
        try:
            question = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not question:
            continue
        if question in ("/quit", "/exit"):
            break
        if question == "/reset":
            history = []
            print("Conversation cleared.\n")
            continue
        if question == "/sources":
            print_sources(last)
            continue

        try:
            last = assistant.ask(question, history)
        except LLMError as e:
            print("\n%s\n" % e)
            continue
        print_answer(last)
        history.append({"question": question, "answer": last["answer"]})


if __name__ == "__main__":
    main()
