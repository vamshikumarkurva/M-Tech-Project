# Copyright 2015 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Binary for training translation models and decoding from them.
Running this program without --decode will download the WMT corpus into
the directory specified as --data_dir and tokenize it in a very basic way,
and then start training a model saving checkpoints to --train_dir.
Running with --decode starts an interactive loop so you can see how
the current checkpoint translates English sentences into French.
See the following papers for more information on neural translation models.
 * http://arxiv.org/abs/1409.3215
 * http://arxiv.org/abs/1409.0473
 * http://arxiv.org/abs/1412.2007
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import math
import os
import random
import sys
import time

import numpy as np
from six.moves import xrange  # pylint: disable=redefined-builtin
import tensorflow as tf

import data_utils
import seq2seq_model


tf.app.flags.DEFINE_float("learning_rate", 0.5, "Learning rate.")
tf.app.flags.DEFINE_float("learning_rate_decay_factor", 0.99,
                          "Learning rate decays by this much.")
tf.app.flags.DEFINE_float("max_gradient_norm", 5.0,
                          "Clip gradients to this norm.")
tf.app.flags.DEFINE_integer("batch_size", 64,
                            "Batch size to use during training.")
tf.app.flags.DEFINE_integer("embedding_size", 32,
                            "size of word embeddings")
tf.app.flags.DEFINE_integer("size", 1024, "Size of each model layer.")
tf.app.flags.DEFINE_integer("num_layers", 3, "Number of layers in the model.")
tf.app.flags.DEFINE_integer("eng_vocab_size", 40000, "English vocabulary size.")
tf.app.flags.DEFINE_integer("hin_vocab_size", 40000, "Hindi vocabulary size.")
tf.app.flags.DEFINE_string("data_dir", "/tmp", "Data directory")
tf.app.flags.DEFINE_string("train_dir", "/tmp", "Training directory.")
tf.app.flags.DEFINE_integer("max_train_data_size", 0,
                            "Limit on the size of training data (0: no limit).")
tf.app.flags.DEFINE_integer("steps_per_checkpoint", 200,
                            "How many training steps to do per checkpoint.")
tf.app.flags.DEFINE_boolean("decode", False,
                            "Set to True for interactive decoding.")
tf.app.flags.DEFINE_boolean("decode_all", False,
                            "Set to True for decoding all at once.")
tf.app.flags.DEFINE_boolean("self_test", False,
                            "Run a self-test if this is set to True.")
tf.app.flags.DEFINE_boolean("use_fp16", False,
                            "Train using fp16 instead of fp32.")

FLAGS = tf.app.flags.FLAGS

# We use a number of buckets and pad to the closest one for efficiency.
# See seq2seq_model.Seq2SeqModel for details of how they work.
_buckets = [(10,15),(20,25),(35,35)]

def exp_decay(i):
  i_t = float(i)
  k = 0.999995
  if i_t < 50000:
    return 1.0
  else: 
    return np.power(k, i_t-50000)  

def sampling(eps, iteration, decoder_size):
  k = []
  for i in range(decoder_size):
    rand = np.random.random_sample()
    k.append(rand)
  k = np.array(k)
  return k < eps

def read_data(source_path, target_path, max_size=None):
  """Read data from source and target files and put into buckets.
  Args:
    source_path: path to the files with token-ids for the source language.
    target_path: path to the file with token-ids for the target language;
      it must be aligned with the source file: n-th line contains the desired
      output for n-th line from the source_path.
    max_size: maximum number of lines to read, all other will be ignored;
      if 0 or None, data files will be read completely (no limit).
  Returns:
    data_set: a list of length len(_buckets); data_set[n] contains a list of
      (source, target) pairs read from the provided data files that fit
      into the n-th bucket, i.e., such that len(source) < _buckets[n][0] and
      len(target) < _buckets[n][1]; source and target are lists of token-ids.
  """
  data_set = [[] for _ in _buckets]
  with tf.gfile.GFile(source_path, mode="r") as source_file:
    with tf.gfile.GFile(target_path, mode="r") as target_file:
      source, target = source_file.readline(), target_file.readline()
      counter = 0
      while source and target and (not max_size or counter < max_size):
        counter += 1
        if counter % 100000 == 0:
          print("  reading data line %d" % counter)
          sys.stdout.flush()
        source_ids = [int(x) for x in source.split()]
        target_ids = [int(x) for x in target.split()]
        target_ids.append(data_utils.EOS_ID)
        for bucket_id, (source_size, target_size) in enumerate(_buckets):
          if len(source_ids) < source_size and len(target_ids) < target_size:
            data_set[bucket_id].append([source_ids, target_ids])
            break
        source, target = source_file.readline(), target_file.readline()
  return data_set


def create_model(session, forward_only):
  """Create translation model and initialize or load parameters in session."""
  dtype = tf.float16 if FLAGS.use_fp16 else tf.float32
  model = seq2seq_model.Seq2SeqModel(
      FLAGS.eng_vocab_size,
      FLAGS.hin_vocab_size,
      _buckets,
      FLAGS.size,
      FLAGS.num_layers,
      FLAGS.max_gradient_norm,
      FLAGS.batch_size,
      FLAGS.embedding_size,
      FLAGS.learning_rate,
      FLAGS.learning_rate_decay_factor,
      use_lstm=False,
      forward_only=forward_only,
      dtype = dtype)
  ckpt = tf.train.get_checkpoint_state(FLAGS.train_dir)
  if ckpt and tf.gfile.Exists(ckpt.model_checkpoint_path):
    print("Reading model parameters from %s" % ckpt.model_checkpoint_path)
    model.saver.restore(session, ckpt.model_checkpoint_path)
  else:
    print("Created model with fresh parameters.")
    session.run(tf.initialize_all_variables())
  return model


def train():
  """Train a en->fr translation model using WMT data."""
  # Prepare WMT data.
  print("Preparing WMT data in %s" % FLAGS.data_dir)
  en_train, fr_train, en_dev, fr_dev, _, _ = data_utils.prepare_wmt_data(
      FLAGS.data_dir, FLAGS.eng_vocab_size, FLAGS.hin_vocab_size)

  save_path = os.path.join(FLAGS.train_dir, "summary/")
  with tf.Session() as sess:
    # Create model.
    print("Creating %d layers of %d units." % (FLAGS.num_layers, FLAGS.size))
    model = create_model(sess, False)
    test_writer = tf.train.SummaryWriter(os.path.join(save_path,'test'), graph=sess.graph)
    train_writer = tf.train.SummaryWriter(os.path.join(save_path,'train'), graph=sess.graph)

    # Read data into buckets and compute their sizes.
    print ("Reading development and training data (limit: %d)."
           % FLAGS.max_train_data_size)
    dev_set = read_data(en_dev, fr_dev)
    train_set = read_data(en_train, fr_train, FLAGS.max_train_data_size)
    train_bucket_sizes = [len(train_set[b]) for b in xrange(len(_buckets))]
    train_total_size = float(sum(train_bucket_sizes))

    # A bucket scale is a list of increasing numbers from 0 to 1 that we'll use
    # to select a bucket. Length of [scale[i], scale[i+1]] is proportional to
    # the size if i-th training bucket, as used later.
    train_buckets_scale = [sum(train_bucket_sizes[:i + 1]) / train_total_size
                           for i in xrange(len(train_bucket_sizes))]

    # This is the training loop.
    step_time, loss = 0.0, 0.0
    current_step = 0
    previous_losses = []
    perplexity_eval_summary = tf.Summary()
    perplexity_train_summary = tf.Summary()
    eps1 = exp_decay(float("inf"))
    #print(eps1)
    decode1 = sampling(eps1, float("inf"), _buckets[-1][1]+1)

    while current_step < 80001:
      # Choose a bucket according to data distribution. We pick a random number
      # in [0, 1] and use the corresponding interval in train_buckets_scale.
      random_number_01 = np.random.random_sample()
      bucket_id = min([i for i in xrange(len(train_buckets_scale))
                       if train_buckets_scale[i] > random_number_01])
      eps = exp_decay(current_step*1.0)
      #print(eps)
      decode = sampling(eps, current_step*1.0, _buckets[-1][1]+1)
      # Get a batch and make a step.
      start_time = time.time()
      encoder_inputs, decoder_inputs, target_weights = model.get_batch(
          train_set, bucket_id)
      _, step_loss, _, _ = model.step(sess, encoder_inputs, decoder_inputs,
                                   target_weights, bucket_id, decode, False)
      step_time += (time.time() - start_time) / FLAGS.steps_per_checkpoint
      #loss += step_loss / FLAGS.steps_per_checkpoint
      loss = step_loss
      current_step += 1

      # Once in a while, we save checkpoint, print statistics, and run evals.
      if current_step % FLAGS.steps_per_checkpoint == 0:
        # Print statistics for the previous epoch.
        perplexity = math.exp(float(loss)) if loss < 300 else float("inf")
        bucket_trainvalue = perplexity_train_summary.value.add()
        bucket_trainvalue.tag = "peplexity_trainbucket_%d" % bucket_id
        bucket_trainvalue.simple_value = perplexity
        train_writer.add_summary(perplexity_train_summary, model.global_step.eval())
        print ("global step %d learning rate %.4f step-time %.2f perplexity "
               "%.2f bucketid: %d epsilon: %f" % (model.global_step.eval(), model.learning_rate.eval(),
                         step_time, perplexity, bucket_id, eps))
        # Decrease learning rate if no improvement was seen over last 3 times.
        if len(previous_losses) > 2 and loss > max(previous_losses[-3:]):
          sess.run(model.learning_rate_decay_op)
        learning_rate = tf.scalar_summary('learning_rate',model.learning_rate_decay_op)
        learning_str = sess.run(learning_rate)
        train_writer.add_summary(learning_str,model.global_step.eval())
        previous_losses.append(loss)
        # Save checkpoint and zero timer and loss.
        checkpoint_path = os.path.join(FLAGS.train_dir, "translate.ckpt")
        model.saver.save(sess, checkpoint_path, global_step=model.global_step)
        step_time, loss = 0.0, 0.0
        # Run evals on development set and print their perplexity.
        for bucket_id in xrange(len(_buckets)):
          if len(dev_set[bucket_id]) == 0:
            print("  eval: empty bucket %d" % (bucket_id))
            continue
          encoder_inputs, decoder_inputs, target_weights = model.get_batch(
              dev_set, bucket_id)
          _, eval_loss, _, _ = model.step(sess, encoder_inputs, decoder_inputs,
                                       target_weights, bucket_id, decode1, True)
          eval_ppx = math.exp(float(eval_loss)) if eval_loss < 300 else float(
              "inf")
          bucket_value = perplexity_eval_summary.value.add()
          bucket_value.tag = "peplexity_evalbucket_%d" % bucket_id
          bucket_value.simple_value = eval_ppx
          test_writer.add_summary(perplexity_eval_summary, model.global_step.eval())
          print("  eval: bucket %d perplexity %.2f" % (bucket_id, eval_ppx))
        sys.stdout.flush()


def decode():
  with tf.Session() as sess:
    # Create model and load parameters.
    model = create_model(sess, True)
    model.batch_size = 1  # We decode one sentence at a time.

    # Load vocabularies.
    en_vocab_path = os.path.join(FLAGS.data_dir,
                                 "vocab%d.eng" % FLAGS.eng_vocab_size)
    fr_vocab_path = os.path.join(FLAGS.data_dir,
                                 "vocab%d.hin" % FLAGS.hin_vocab_size)
    en_vocab, _ = data_utils.initialize_vocabulary(en_vocab_path)
    _, rev_fr_vocab = data_utils.initialize_vocabulary(fr_vocab_path)

    # Decode from standard input.
    sys.stdout.write("> ")
    sys.stdout.flush()
    sentence = sys.stdin.readline()
    eps = exp_decay(float("inf"))
    print(eps)
    decode = sampling(eps, float("inf"), _buckets[-1][1]+1)
    while sentence:
      # Get token-ids for the input sentence.
      token_ids = data_utils.sentence_to_token_ids(sentence, en_vocab)
      # Which bucket does it belong to?
      bucket_id = min([b for b in xrange(len(_buckets))
                       if _buckets[b][0] > len(token_ids)])

      # Get a 1-element batch to feed the sentence to the model.
      encoder_inputs, decoder_inputs, target_weights = model.get_batch(
          {bucket_id: [(token_ids, [])]}, bucket_id)
      # Get output logits for the sentence.
      _, _, output_logits, state = model.step(sess, encoder_inputs, decoder_inputs,
                                       target_weights, bucket_id, decode, True)
      # This is a greedy decoder - outputs are just argmaxes of output_logits.
      outputs = [int(np.argmax(logit, axis=1)) for logit in output_logits]
      # probabilities
      probs = [np.max(logit, axis=1) for logit in output_logits]
      # If there is an EOS symbol in outputs, cut them at that point.
      if data_utils.EOS_ID in outputs:
        outputs = outputs[:outputs.index(data_utils.EOS_ID)]
      x = len(outputs)
      probs = probs[:x]
      conf_score = 0.0
      for prob in probs:
        #print(prob)
        conf_score += prob
      print("Confidence score:", conf_score)
      # Print out French sentence corresponding to outputs.
      sentence2 = " ".join([rev_fr_vocab[output] for output in outputs])
      #sentence2 = [tf.compat.as_str(rev_fr_vocab[output]) for output in outputs]
      print(sentence2)
      f = open('answer.txt','a')
      f.write(sentence2+"\n")
      f.close()
      print("> ", end="")
      sys.stdout.flush()
      sentence = sys.stdin.readline()

def decode_all():
  with tf.Session() as sess:
    # Create model and load parameters.
    model = create_model(sess, True)
    model.batch_size = 1  # We decode one sentence at a time.

    # Load vocabularies.
    en_vocab_path = os.path.join(FLAGS.data_dir,
                                 "vocab%d.eng" % FLAGS.eng_vocab_size)
    fr_vocab_path = os.path.join(FLAGS.data_dir,
                                 "vocab%d.hin" % FLAGS.hin_vocab_size)
    en_vocab, _ = data_utils.initialize_vocabulary(en_vocab_path)
    _, rev_fr_vocab = data_utils.initialize_vocabulary(fr_vocab_path)

    # Decode from standard input.
    #sys.stdout.write("> ")
    #sys.stdout.flush()
    #sentence = sys.stdin.readline()
    f = open('train1.eng','r')
    g = open('decoded.hin','w')
    i = 0
    eps = exp_decay(float("inf"))
    print(eps)
    decode = sampling(eps, float("inf"), _buckets[-1][1]+1)

    for line in f:
      # Get token-ids for the input sentence.
      sentence = line.strip()
      print(i)
      i += 1
      token_ids = data_utils.sentence_to_token_ids(sentence, en_vocab)
      # Which bucket does it belong to?
      bucket_id = min([b for b in xrange(len(_buckets))
                       if _buckets[b][0] > len(token_ids)])
      # Get a 1-element batch to feed the sentence to the model.
      encoder_inputs, decoder_inputs, target_weights = model.get_batch(
          {bucket_id: [(token_ids, [])]}, bucket_id)
      # Get output logits for the sentence.
      _, _, output_logits, state = model.step(sess, encoder_inputs, decoder_inputs,
                                       target_weights, bucket_id, decode, True)
      # This is a greedy decoder - outputs are just argmaxes of output_logits.
      outputs = [int(np.argmax(logit, axis=1)) for logit in output_logits]
      # probabilities
      probs = [np.max(logit, axis=1) for logit in output_logits]
      # If there is an EOS symbol in outputs, cut them at that point.
      if data_utils.EOS_ID in outputs:
        outputs = outputs[:outputs.index(data_utils.EOS_ID)]
      x = len(outputs)
      probs = probs[:x]
      conf_score = 0.0
      for prob in probs:
        #print(prob)
        conf_score += prob
      #print("Confidence score:", conf_score)
      # Print out French sentence corresponding to outputs.
      sentence2 = " ".join([rev_fr_vocab[output] for output in outputs])
      #sentence2 = [tf.compat.as_str(rev_fr_vocab[output]) for output in outputs]
      #print(sentence2)
      g.write(sentence2+"\n")
      #print("> ", end="")
      #sys.stdout.flush()
      #sentence = sys.stdin.readline()

def self_test():
  """Test the translation model."""
  with tf.Session() as sess:
    print("Self-test for neural translation model.")
    # Create model with vocabularies of 10, 2 small buckets, 2 layers of 32.
    model = seq2seq_model.Seq2SeqModel(10, 10, [(3, 3), (6, 6)], 32, 2,
                                       5.0, 32, 0.3, 0.99, num_samples=8)
    sess.run(tf.initialize_all_variables())

    # Fake data set for both the (3, 3) and (6, 6) bucket.
    data_set = ([([1, 1], [2, 2]), ([3, 3], [4]), ([5], [6])],
                [([1, 1, 1, 1, 1], [2, 2, 2, 2, 2]), ([3, 3, 3], [5, 6])])
    for _ in xrange(5):  # Train the fake model for 5 steps.
      bucket_id = random.choice([0, 1])
      encoder_inputs, decoder_inputs, target_weights = model.get_batch(
          data_set, bucket_id)
      model.step(sess, encoder_inputs, decoder_inputs, target_weights,
                 bucket_id, False)


def main(_):
  if FLAGS.self_test:
    self_test()
  elif FLAGS.decode:
    decode()
  elif FLAGS.decode_all:
    decode_all()
  else:
    train()

if __name__ == "__main__":
  tf.app.run()
