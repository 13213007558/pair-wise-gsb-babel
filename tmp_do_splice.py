from pathlib import Path

def read(name):
    content = Path(name).read_text()
    # apply_patch added a trailing newline; drop it
    if content.endswith("\n\n"):
        content = content[:-1]
    return content

TEXT_A = read("tmp_textA.py")
TEXT_B_OLD = read("tmp_textB_old.py")
TEXT_B_NEW = read("tmp_textB_new.py")
SPLICE_C = read("tmp_spliceC.py")

path = Path("babel/messages/extract.py")
text = path.read_text()

anchor_a = "    in_def = in_translator_comments = False\n    comment_tag = None\n"
assert text.count(anchor_a) == 1, "anchor A"
text = text.replace(anchor_a, anchor_a + TEXT_A, 1)

assert text.count(TEXT_B_OLD) == 1, "anchor B"
text = text.replace(TEXT_B_OLD, TEXT_B_NEW, 1)

start = "        elif funcname and len(call_stack) == 1:\n"
end = "        elif len(call_stack) > 1 and tok == OP and value == ')':"
assert text.count(start) == 1, "start C"
assert text.count(end) == 1, "end C"
i = text.index(start)
j = text.index(end)
assert i < j
text = text[:i] + SPLICE_C + text[j:]

path.write_text(text)
print("splices applied")

