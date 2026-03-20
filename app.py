import os
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
import feedparser
from deep_translator import GoogleTranslator
from datetime import datetime
import threading

app = Flask(__name__)

# --- データベース設定 ---
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'news.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- データベースモデル ---
class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    url = db.Column(db.String(500), nullable=False, unique=True)
    category = db.Column(db.String(50), nullable=False)
    published_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_translated = db.Column(db.Boolean, default=True)

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200))

# --- データ取得・自動分類ロジック ---
def fetch_and_save_data():
    print("--- Data Update Started ---")
    with app.app_context():
        # 1. YouTube更新
        try:
            from youtubesearchpython import VideosSearch
            print("Searching YouTube...")
            search = VideosSearch('ホルムズ海峡 情勢 解説', limit=5)
            result = search.result()
            
            if result and 'result' in result:
                found_vid = None
                for item in result['result']:
                    if item.get('type') == 'video':
                        found_vid = item['id']
                        found_title = item['title']
                        break
                
                if found_vid:
                    print(f"SUCCESS: Found Video -> {found_vid}")
                    record = Video.query.first()
                    if not record:
                        db.session.add(Video(video_id=found_vid, title=found_title))
                    else:
                        record.video_id = found_vid
                        record.title = found_title
                    db.session.commit()
        except Exception as e:
            print(f"YouTube Error: {e}")

        # 2. ニュース更新（二重登録バグを修正）
        try:
            urls = {
                'main': 'https://news.google.com/rss/search?q=Hormuz+Strait+oil+shipping&hl=en-US&gl=US&ceid=US:en',
                'market': 'https://news.google.com/rss/search?q=Naphtha+price+market&hl=en-US&gl=US&ceid=US:en'
            }
            translator = GoogleTranslator(source='en', target='ja')
            
            for base_cat, rss_url in urls.items():
                feed = feedparser.parse(rss_url)
                for entry in feed.entries[:3]:
                    if not News.query.filter_by(url=entry.link).first():
                        t_title = translator.translate(entry.title)
                        
                        # カテゴリの自動判定
                        final_cat = base_cat
                        if any(kw in t_title for kw in ['ゴム', 'ホース', 'NBR', 'HNBR', 'タイヤ']):
                            final_cat = 'tire'
                        elif any(kw in t_title for kw in ['化学', 'プラント', 'ナフサ']):
                            final_cat = 'chemical'
                        
                        # 1回だけ保存
                        db.session.add(News(title=t_title, url=entry.link, category=final_cat, is_translated=True))
            db.session.commit()
            print("News Update Completed.")
        except Exception as e:
            print(f"News Error: {e}")
    print("--- Data Update Finished ---")

# --- 初期化 ---
with app.app_context():
    db.create_all()

scheduler = BackgroundScheduler()
scheduler.add_job(func=fetch_and_save_data, trigger="interval", hours=1)
scheduler.start()

# 起動直後に実行
threading.Thread(target=fetch_and_save_data).start()

# --- ルーティング ---
@app.route('/')
def index():
    all_news = News.query.order_by(News.published_at.desc()).limit(15).all()
    video = Video.query.first()
    v_id = video.video_id if video else "r2Do5g2QzXk"
    return render_template('index.html', main_news=all_news, video_id=v_id, title="総合概況")

@app.route('/chemical')
def chemical():
    news = News.query.filter_by(category='chemical').order_by(News.published_at.desc()).all()
    video = Video.query.first()
    v_id = video.video_id if video else "r2Do5g2QzXk"
    return render_template('index.html', main_news=news, title="化学メーカー関連", video_id=v_id)

@app.route('/tire')
def tire():
    news = News.query.filter_by(category='tire').order_by(News.published_at.desc()).all()
    video = Video.query.first()
    v_id = video.video_id if video else "r2Do5g2QzXk"
    return render_template('index.html', main_news=news, title="タイヤ・ホース関連", video_id=v_id)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
