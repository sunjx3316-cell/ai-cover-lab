# Privacy

The application binds to `127.0.0.1` and processes audio locally. Gradio analytics
and Weights & Biases logging are disabled. The offline release disables Hugging
Face network downloads. Online Setup.cmd downloads dependencies and model files.

Recordings, training datasets, generated tracks and logs remain in the install
directory until you remove them. They are not automatically uploaded to GitHub.
The public release includes only the separately authorized voice weights/index,
not its training recordings or the publisher's generated songs.

Browsers, Windows and GPU drivers may independently make network requests; this
document does not claim to control those programs. Do not expose the local server
through a public tunnel. Redact file paths and private audio from issue reports.
