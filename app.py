import os
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
import feedparser
from deep_translator import GoogleTranslator
from datetime import datetime

app = Flask(__name__)

# データベースの設定（Renderの環境でも動作するように設定）
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_DATA'] = 'sqlite:///' + os.path.join(basedir, 'news.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# データベースモデルの定義
class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    url = db.Column(db.String(500), nullable=False, unique=True)
    category = db.Column(db.String(50), nullable=False)
    published_at = db.Column(db.DateTime, default=datetime.utcnow)

# ニュースを取得して保存する関数
def fetch_and_save_news():
    rss_urls = {
        'main': 'https://news.google.com/rss/search?q=Hormuz+Strait+oil+shipping&hl=en-US&gl=US&ceid=US:en',
        'market': 'https://news.google.com/rss/search?q=Naphtha+price+market&hl=en-US&gl=US&ceid=US:en'
    }
    
    translator = GoogleTranslator(source='en', target='ja')
    
    with app.app_context():
        for category, url in rss_urls.items():
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:  # 各カテゴリ最新5件
                # 重複チェック
                if not News.query.filter_by(url=entry.link).first():
                    try:
                        translated_title = translator.translate(entry.title)
                        new_news = News(
                            title=translated_title,
                            url=entry.link,
                            category=category
                        )
                        db.session.add(new_news)
                    except Exception as e:
                        print(f"Error translating/saving: {e}")
        db.session.commit()

# スケジューラーの設定（1時間ごとに更新）
scheduler = BackgroundScheduler()
scheduler.add_job(func=fetch_and_save_news, trigger="interval", hours=1)
scheduler.start()

@app.route('/')
def index():
    # データベースからニュースを取得して表示
    main_news = News.query.filter_by(category='main').order_by(News.published_at.desc()).limit(10).all()
    market_news = News.query.filter_by(category='market').order_by(News.published_at.desc()).limit(10).all()
    return render_template('index.html', main_news=main_news, market_news=market_news)

if __name__ == '__main__':
    # 起動時にデータベースとテーブルを作成し、最初のニュースを取得
    with app.app_context():
        db.create_all()
        fetch_and_save_news()
    
    # Render等の本番環境用に host='0.0.0.0' を指定
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
