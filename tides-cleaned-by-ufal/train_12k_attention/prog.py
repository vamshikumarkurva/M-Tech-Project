f = open('log.txt','r')
import matplotlib.pyplot as plt
from scipy.interpolate import spline
import numpy as np

train_0 = []
train_1 = []
train_2 = []
test_0 = []
test_1 = []
test_2 = []
train = []

for i, line in enumerate(f):
  line = line.strip()
  words = line.split()
  #print(words)
  rem = i%4
  div = i/4
  if rem == 0:
    step = int(words[2])
    bucket = int(words[-1])
    perplexity = float(words[9])
    '''
    if bucket == 0:
      train_0.append((step,perplexity))
    elif bucket==1:
      train_1.append((step,perplexity))
    else:
      train_2.append((step,perplexity))'''
    train.append((step, perplexity))
  elif rem == 1:
    step = 200*(div+1)
    perplexity = float(words[-1])
    test_0.append((step, perplexity))
  elif rem == 2:
    step = 200*(div+1)
    perplexity = float(words[-1])
    test_1.append((step, perplexity))
  else:
    step = 200*(div+1)
    perplexity = float(words[-1])
    test_2.append((step, perplexity))

f.close()
step = [x[0] for x in train]
step_new = np.linspace(200,40000,800)
train_err = [k[1] for k in train]
train_err_smooth = spline(step, train_err, step_new)
test_err0 = [k[1] for k in test_0]
test_err0_smooth = spline(step, test_err0, step_new)
test_err1 = [k[1] for k in test_1]
test_err1_smooth = spline(step, test_err1, step_new)
test_err2 = [k[1] for k in test_2]
test_err2_smooth = spline(step, test_err2, step_new)
lw=2

plt.plot(step_new, train_err_smooth, color = 'navy', lw=lw, label = 'training error')
plt.hold('on')
plt.plot(step_new, test_err0_smooth, color = 'c', lw=lw, label = 'validation error')
#plt.hold('on')
#plt.plot(step_new, test_err1_smooth, color = 'k', lw=lw, label = 'bucket_1')
#plt.hold('on')
#plt.plot(step_new, test_err2_smooth, color = 'g', lw=lw, label = 'bucket_2')

'''
plt.plot(step, train_err, color = 'navy', lw=lw, label = 'training error')
plt.hold('on')
plt.plot(step, test_err, color = 'c', lw=lw, label = 'validation error')'''

plt.xlabel('------> Iterations')
plt.ylabel('------> Perplexity')
plt.title('error plot')
plt.legend()
plt.show()

