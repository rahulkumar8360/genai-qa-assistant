# The question-answering pipeline, one step per module:
#
#   loader     read .txt / .md / .pdf files into pages of text
#   chunker    cut pages into small overlapping passages, keeping the heading
#   retriever  rank passages against a question (BM25)
#   prompts    turn the passages + question into a system prompt and messages
#   llm        send that request to a backend (Claude, or the offline stand-in)
#   assistant  wire the steps together and parse citations out of the answer
#
# Each module only knows about the one before it, so any step can be swapped
# (a different retriever, a different model) without touching the others.
