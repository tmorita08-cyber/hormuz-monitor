import os
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
import feedparser
from deep_translator import GoogleTranslator
from datetime import datetime

app = Flask(__name__)

# データベース設定
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'news.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# データベースモデル
class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    url = db.Column(db.String(500), nullable=False, unique=True)
    category = db.Column(db.String(50), nullable=False) # 'main', 'market', 'tire', 'chemical'
    published_at = db.Column(db.DateTime, default=datetime.utcnow)

# ニュース取得・自動分類ロジック
def fetch_and_save_news():
    rss_urls = {
        'main': 'https://news.google.com/rss/search?q=Hormuz+Strait+oil+shipping&hl=en-US&gl=US&ceid=US:en',
        'market': 'https://news.google.com/rss/search?q=Naphtha+price+market&hl=en-US&gl=US&ceid=US:en'
    }
    
    # 分類用キーワード設定
    keywords = {
        'tire': ['タイヤ', 'ブリヂストン', '横浜ゴム', '住友ゴム', 'ゴム', 'ホース', 'コンパウンド'],
        'chemical': ['化学', 'プラント', 'エチレン', '三菱ケミカル', '三井化学', '旭化成', '石油化学']
    }
    
    translator = GoogleTranslator(source='en', target='ja')
    
    with app.app_context():
        for base_cat, url in rss_urls.items():
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                if not News.query.filter_by(url=entry.link).first():
                    try:
                        translated_title = translator.translate(entry.title)
                        
                        # キーワードによる自動カテゴリ判定
                        final_category = base_cat
                        for cat_name, word_list in keywords.items():
                            if any(word in translated_title for word in word_list):
                                final_category = cat_name
                                break
                        
                        new_news = News(
                            title=translated_title,
                            url=entry.link,
                            category=final_category
                        )
                        db.session.add(new_news)
                    except Exception as e:
                        print(f"Error: {e}")
        db.session.commit()

# 起動時に実行
with app.app_context():
    db.create_all()
    fetch_and_save_news()

# 定期実行設定（1時間おき）
scheduler = BackgroundScheduler()
scheduler.add_job(func=fetch_and_save_news, trigger="interval", hours=1)
scheduler.start()

# --- ルーティング ---

@app.route('/')
def index():
    # 全カテゴリから最新順に取得
    all_news = News.query.order_by(News.published_at.desc()).limit(15).all()
    return render_template('index.html', main_news=all_news)

@app.route('/chemical')
def chemical():
    news = News.query.filter_by(category='chemical').order_by(News.published_at.desc()).all()
    return render_template('index.html', main_news=news, title="化学メーカー関連")

@app.route('/tire')
def tire():
    news = News.query.filter_by(category='tire').order_by(News.published_at.desc()).all()
    return render_template('index.html', main_news=news, title="タイヤ・ホース関連")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
