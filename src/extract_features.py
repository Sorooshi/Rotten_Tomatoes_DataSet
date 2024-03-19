import numpy as np
import pandas as pd
import tensorflow as tf
import keras_tuner as kt 
from sklearn.model_selection import train_test_split


tfk = tf.keras 
tfkl = tf.keras.layers
BATCH_SIZE = 8

class LstmAe(tfk.Model):
    def __init__(self, latent_dim, vocabulary, *args, **kwargs):
        super(LstmAe, self).__init__(*args, **kwargs)
        self.max_seq_len = 100
        # self.loss_tracker = tfk.metrics.Mean(name="loss")
        self.train_metric = tfk.metrics.MeanAbsoluteError(name="mae")
        self.val_metric = tfk.metrics.MeanAbsoluteError(name="mae")
        self.loss_fn = tfk.losses.MeanSquaredError(name="mse_loss")


        self.inputs = tfkl.InputLayer(
            input_shape=(1,), dtype=tf.string,
            )
        self.txt_vec = tfkl.TextVectorization(
            max_tokens=None, 
            vocabulary = vocabulary,
            split="whitespace", ngrams=1, 
            output_mode="int", ragged=False,
            output_sequence_length=self.max_seq_len,
            standardize="lower_and_strip_punctuation",
            )

        self.emb = tfkl.Embedding(
            input_dim=self.txt_vec.vocabulary_size(),
            output_dim=latent_dim,
            )
        self.enc1 = tfkl.Bidirectional(
            tfkl.LSTM(
                units=100,  # hp.Int('units', min_value=2, max_value=100, step=5), 
                activation="relu",  # hp.Choice("activation", ["relu", "tanh"]), 
                # dropout=hp.Float('dropout', min_value=0.0, max_value=0.5, step=0.1),
                return_sequences=True,
                name="encoder1"
                )
            )
        
        self.enc2 = tfkl.Bidirectional(
            tfkl.LSTM(
                units=50,  # hp.Int('units', min_value=2, max_value=100, step=5), 
                activation="relu",  # hp.Choice("activation", ["relu", "tanh"]), 
                # dropout=hp.Float('dropout', min_value=0.0, max_value=0.5, step=0.1),
                return_sequences=True,
                name="encoder1"
                )
            )
        self.dec1 = tfkl.Bidirectional(
            tfkl.LSTM(
                units=50,  # hp.Int('units', min_value=2, max_value=100, step=5), 
                activation="relu",  # hp.Choice("activation", ["relu", "tanh"]), 
                # dropout=hp.Float('dropout', min_value=0.0, max_value=0.5, step=0.1),
                return_sequences=True,
                name="decoder1"
            )
        )
        self.dec2 = tfkl.Bidirectional(
            tfkl.LSTM(
                units=100,  # hp.Int('units', min_value=2, max_value=100, step=5), 
                activation="tanh",  # hp.Choice("activation", ["relu", "tanh"]), 
                # dropout=hp.Float('dropout', min_value=0.0, max_value=0.5, step=0.1),
                return_sequences=False,
                name="decoder2"
                )
            )
        self.outputs = tfkl.Dense(
            units=self.max_seq_len, activation="softmax"
            )

    def call(self, inputs, training=None):
        x = self.inputs(inputs, training)
        x = self.txt_vec(x)
        x = self.emb(x)
        x = self.enc1(x)
        x = self.enc2(x)
        x = self.dec1(x)
        x = self.dec2(x)
        x = self.outputs(x)
        return x 
    
    @tf.function
    def train_step(self, x, y):
        with tf.GradientTape() as tape:
            y_pred = self(x, training=True)
            if y is None:
                y_true = self.inputs(self.txt_vec(x))
            else:
                y_true = self.inputs(self.txt_vec(y))
            loss_value = self.loss_fn(y_true, y_pred)
        grads = tape.gradient(loss_value, self.trainable_weights)
        self.optimizer.apply_gradients(zip(grads, self.trainable_weights))
        self.train_metric.update_state(y_true, y_pred)
        return loss_value
    
    @tf.function
    def test_step(self, x, y):
        y_pred = self(x, training=False)
        if y is None:
            y_true = self.inputs(self.txt_vec(x))
        else:
            y_true = self.inputs(self.txt_vec(y))
        return self.val_metric(y_true, y_pred)

    def fit(self, train_data, test_data, n_epochs):
        train_total_loss, val_total_loss = [], []
        for epoch in range(n_epochs):
            print(f"epoch: {epoch+1}")
            for step, (x_tr_batch, y_tr_batch) in enumerate(train_data):
                loss_value = self.train_step(x_tr_batch, y_tr_batch)
                if step % 50 == 0:
                    print(
                        "Training loss (for one batch) at step %d: %.4f"
                        % (step, loss_value)
                    )
            train_total_loss.append(self.train_metric)
        
            for step, (x_val_batch, y_val_batch) in enumerate(test_data):
                val_loss = self.test_step(x_val_batch, y_val_batch)
                val_total_loss.append(val_loss)
                if step % 25 == 0:
                        print(
                            "Validation loss (for one batch) at step %d: %.4f"
                            % (step, val_loss)
                        )
        return train_total_loss, val_total_loss

class TrainTestLstmAe:
    def __init__(self, data: pd.DataFrame=None, n_epochs: int= 1):
        super().__init__()
        self.data = data
        self.n_epochs = n_epochs
    
    @staticmethod
    def get_vocabulary_and_max_len(
        data_path: str="../data/medium_movies_data.csv", 
        vocab_size: int = 124100 # 124,079 precise
        ) -> tuple:

        data = pd.read_csv(data_path)
        text_data = data.Synopsis.values
        labels = data.Genre.values
        print(
            f"text data head: \n {text_data[:3]} \n" 
            f"text data shape: {text_data.shape} \n"
            f"labels head: \n {labels[:3]} \n"
            f"labels shape: {labels.shape} \n"
        )
        if vocab_size is None:  # a bit slower
            vocabulary = []
            max_seq_len = 0
            for synopsis in text_data:
                parsed_synopsis = np.unique(synopsis.lower().strip().split(" ")).tolist()
                if len(parsed_synopsis) > max_seq_len:
                    max_seq_len = len(parsed_synopsis)
                for word in parsed_synopsis:
                    if word not in vocabulary:
                        vocabulary.append(vocabulary)            
            vocab_size = len(vocabulary)
            n_classes = [i.lower() for i in np.unique(labels)]
            print(
                f"vocabulary size {len(vocabulary)}"
                f"Number of classes: {n_classes}"
                )
        else:
            max_seq_len = 171
        txt_vec = tfkl.TextVectorization(
            max_tokens=vocab_size, 
            split="whitespace", ngrams=1, 
            output_mode="int", ragged=True,
            standardize="lower_and_strip_punctuation",
        )
        txt_vec.adapt(
            data=text_data, batch_size=8, steps=None
        )

        vocabulary = txt_vec.get_vocabulary()

        return vocabulary, max_seq_len

    def get_train_test_data(
        data_path: str="../data/medium_movies_data.csv", 
        ) -> tuple:

        data = pd.read_csv(data_path)
        text_data = data.Synopsis.values
        labels = data.Genre.values
        print(
            f"text data head: \n {text_data[:3]} \n" 
            f"text data shape: {text_data.shape} \n"
            f"labels head: \n {labels[:3]} \n"
            f"labels shape: {labels.shape} \n"
        ) 

        x_train, x_test, _, _ = train_test_split(
            text_data, labels, test_size=0.05
            )

        train_data = tf.data.Dataset.from_tensor_slices((x_train, x_train))
        train_data = train_data.shuffle(buffer_size=1024).batch(batch_size=BATCH_SIZE)
        test_data = tf.data.Dataset.from_tensor_slices((x_test, x_test))
        test_data = test_data.shuffle(buffer_size=1024).batch(batch_size=BATCH_SIZE)

        return train_data, test_data

    def train_val_test(self,):
        vectorized_text, labels, max_len = self.get_preprocess_data(
            data_path="../data/medium_movies_data.scv",
        )
        
        for k in range(5):
            print("....")




