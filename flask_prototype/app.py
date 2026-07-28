from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html', title="Home - Tessera Prototype")

@app.route('/analysis')
def analysis():
    return render_template('index.html', title="Analysis - Tessera Prototype")

@app.route('/settings')
def settings():
    return render_template('index.html', title="Settings - Tessera Prototype")

if __name__ == '__main__':
    app.run(debug=True, port=5000)
