f1 = open('train.eng','r')
f2 = open('train.hin','r')
f3 = open('valid.eng','r')
f4 = open('valid.hin','r')

g1 = open('train1.eng','w')
g2 = open('train1.hin','w')
g3 = open('valid1.eng','w')
g4 = open('valid1.hin','w')


import re
_WORD_SPLIT = re.compile("([.,!?\"':;)(])")
def basic_tokenizer(sentence):
  """Very basic tokenizer: split the sentence into a list of tokens."""
  words = []
  for space_separated_fragment in sentence.strip().split():
    words.extend(re.split(_WORD_SPLIT, space_separated_fragment))
  return [w for w in words if w]

for i,j in zip(f1,f2):
  i = i.strip()
  j = j.strip()
  eng = basic_tokenizer(i)
  hin = basic_tokenizer(j)
  if len(eng) < 31 and len(hin) < 31:
    g1.write(i+"\n")
    g2.write(j+"\n")

for i,j in zip(f3,f4):
  i = i.strip()
  j = j.strip()
  eng = basic_tokenizer(i)
  hin = basic_tokenizer(j)
  if len(eng) < 31 and len(hin) < 31:
    g3.write(i+"\n")
    g4.write(j+"\n")

f1.close()
f2.close()
f3.close()
f4.close()
g1.close()
g2.close()
g3.close()
g4.close()

