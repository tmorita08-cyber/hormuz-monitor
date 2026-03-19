import os
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
import feedparser
from deep_translator import GoogleTranslator
from datetime import datetime
from youtubesearchpython import VideosSearch

app = Flask(__name__)

# データベース設定
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

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200))

# --- データ取得ロジック ---
def fetch_and_save_data():
    with app.app_context():
        # 1. YouTube最新動画の自動取得
        print("Starting YouTube search...")
        try:
            # 検索ワードを少し広げて確実にヒットさせる
            videosSearch = VideosSearch('ホルムズ海峡 ニュース 解説', limit=1)
            result = videosSearch.result()
            
            if result and 'result' in result and len(result['result']) > 0:
                fetched_video_id = result['result'][0]['id']
                fetched_title = result['result'][0]['title']
                
                video_record = Video.query.first()
                if not video_record:
                    new_video = Video(video_id=fetched_video_id, title=fetched_title)
                    db.session.add(new_video)
                else:
                    video_record.video_id = fetched_video_id
                    video_record.title = fetched_title
                
                # ★重要：動画を先に保存確定（コミット）させる
                db.session.commit()
                print(f"YouTube Success: {fetched_title} ({fetched_video_id})")
            else:
                print("YouTube: No results found.")
        except Exception as e:
            print(f"YouTube Error: {e}")
            db.session.rollback()

        # 2. ニュースの取得と分類
        print("Starting News fetch...")
        rss_urls = {
            'main': 'https://news.google.com/rss/search?q=Hormuz+Strait+oil+shipping&hl=en-US&gl=US&ceid=US:en',
            'market': 'https://news.google.com/rss/search?q=Naphtha+price+market&hl=en-US&gl=US&ceid=US:en'
        }
        keywords = {
            'tire': ['タイヤ', 'ブリヂストン', '横浜ゴム', '住友ゴム', 'ゴム', 'ホース', 'コンパウンド', 'NBR', 'HNBR', 'クロロプレン'],
            'chemical': ['化学', 'プラント', 'エチレン', '三菱ケミカル', '三井化学', '旭化成', '石油化学', 'ナフサ']
        }
        
        translator = GoogleTranslator(source='en', target='ja')
        
        for base_cat, url in rss_urls.items():
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                if not News.query.filter_by(url=entry.link).first():
                    try:
                        translated_title = translator.translate(entry.title)
                        final_category = base_cat
                        for cat_name, word_list in keywords.items():
                            if any(word in translated_title for word in word_list):
                                final_category = cat_name
                                break
                        
                        new_news = News(title=translated_title, url=entry.link, category=final_category)
                        db.session.add(new_news)
                    except Exception as e:
                        print(f"News Entry Error: {e}")
        
        db.session.commit()
        print("News Fetch Completed.")

# --- 初期化とスケジュール ---
with app.app_context():
    db.create_all()
    # 起動時に一度実行
    fetch_and_save_data()

scheduler = BackgroundScheduler()
# 1時間おきに実行
scheduler.add_job(func=fetch_and_save_data, trigger="interval", hours=1)
scheduler.start()

# --- ルーティング ---
def get_current_video_id():
    video = Video.query.first()
    # 取得できていない場合はデフォルト値を返す
    return video.video_id if video else "r2Do5g2QzXk"

@app.route('/')
def index():
    all_news = News.query.order_by(News.published_at.desc()).limit(15).all()
    return render_template('index.html', main_news=all_news, video_id=get_current_video_id(), title="総合概況")

@app.route('/chemical')
def chemical():
    news = News.query.filter_by(category
