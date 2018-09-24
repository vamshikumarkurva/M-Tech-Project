f = open('cornell.txt','r')
f1 = open('questions.txt','w')
f2 = open('answers.txt','w')
import nltk

def create_vocabulary(data_path):
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
      tokens = basic_tokenizer(line)
      for word in tokens:
        if word in vocab:
          vocab[word] += 1
        else:
          vocab[word] = 1
  vocab_list = sorted(vocab.items(), key=operator.itemgetter(1), reverse=True)
  vocab_list = [x[1] for x in vocab_list]
  return vocab_list  


for i,line in enumerate(f):
  line = line.strip()
  words = line.split('------>')
  q_len = len(nltk.word_tokenize(words[0]))
  a_len = len(nltk.word_tokenize(words[1]))
  if q_len < 20 and a_len < 20:
    f1.write(words[0]+'\n')
    f2.write(words[1]+'\n')

f.close()
f1.close()
f2.close()

