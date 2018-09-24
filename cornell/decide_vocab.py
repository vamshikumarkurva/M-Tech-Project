import operator
import re
import os
_WORD_SPLIT = re.compile("([.,!?\"':;)(])")
_DIGIT_RE = re.compile(r"\d")
import matplotlib.pyplot as plt
import nltk
import gzip
from tensorflow.python.platform import gfile

def basic_tokenizer(sentence):
  """Very basic tokenizer: split the sentence into a list of tokens."""
  words = []
  for space_separated_fragment in sentence.strip().split():
    words.extend(re.split(_WORD_SPLIT, space_separated_fragment))
  return [w for w in words if w]


def create_vocabulary(data_path, tokenizer=None):
  """Create vocabulary file (if it does not exist yet) from data file.
  Data file is assumed to contain one sentence per line. Each sentence is
  tokenized and digits are normalized (if normalize_digits is set).
  Vocabulary contains the most-frequent tokens up to max_vocabulary_size.
  We write it to vocabulary_path in a one-token-per-line format, so that later
  token in the first line gets id=0, second line gets id=1, and so on.
  Args:
    vocabulary_path: path where the vocabulary will be created.
    data_path: data file that will be used to create vocabulary.
    max_vocabulary_size: limit on the size of the created vocabulary.
    tokenizer: a function to use to tokenize each data sentence;
      if None, basic_tokenizer will be used.
    normalize_digits: Boolean; if true, all digits are replaced by 0s.
  """
  print("Creating vocabulary from data %s" % (data_path))
  vocab = {}
  with gfile.GFile(data_path, mode="r") as f:
    counter = 0
    for line in f:
      counter += 1
      if counter % 100000 == 0:
        print("  processing line %d" % counter)
      tokens = tokenizer(line)
      for word in tokens:
        if word in vocab:
          vocab[word] += 1
        else:
          vocab[word] = 1
  vocab_list = sorted(vocab.items(), key=operator.itemgetter(1), reverse=True)
  vocab_list = [x[1] for x in vocab_list]
  return vocab_list  
    

data_dir='/home/philips/Downloads/cornell2/'
dev_name = 'questions_dev'
train_name = 'questions_train'
dev_path = os.path.join(data_dir, dev_name)
train_path = os.path.join(data_dir, train_name)
#print(train_path)

# Create vocabularies of the appropriate sizes.
en_list = create_vocabulary(train_path + ".en", tokenizer=nltk.word_tokenize)
print('Eng vocabulary: ', len(en_list))
print(sum(en_list[:12000])/(sum(en_list)*1.0))
fr_list = create_vocabulary(train_path + ".fr", tokenizer=nltk.word_tokenize)
print("Hin Vocabulary: ",len(fr_list))
print(sum(fr_list[:12000])/(sum(fr_list)*1.0))

L = max(len(en_list),len(fr_list))
if L == len(en_list):
  d = len(en_list)-len(fr_list)
  x = [0]*d
  fr_list = fr_list + x
else:
  d = len(fr_list)-len(en_list)
  x = [0]*d
  en_list = en_list + x

x = range(0,L)
lw = 1
plt.plot(x[11000:12000], en_list[11000:12000], color = 'navy', lw=lw, label = 'english vocab')
plt.hold('on')
plt.plot(x[11000:12000], fr_list[11000:12000], color = 'c', lw=lw, label = 'hindi vocab')
plt.hold('on')
plt.xlabel('------> vocabulary')
plt.ylabel('------> frequency')
plt.title('frequency of vocabulary')
plt.legend()
plt.show()
