import os
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
import feedparser
from deep_translator import GoogleTranslator
from datetime import datetime
import threading

# 1. アプリ本体の作成
app = Flask(__name__)

# 2. データベース設定（先に設定を確定させる）
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'news.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 3. SQLAlchemyの初期化（config設定後に紐付け）
db = SQLAlchemy(app)

# --- データベースモデル ---
class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    url = db.Column(db.String(500), nullable=False, unique=True)
    category = db.Column(db.String(50), nullable=False)
    published_at = db.Column(db.DateTime, default=datetime.utcnow)
    # エラーログに出ていた "is_translated" カラムを追加して整合性を取る
    is_translated = db.Column(db.Boolean, default=True)

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200))

# --- データ取得・自動分類ロジック ---
def fetch_and_save_data():
    with app.app_context():
        # YouTube検索ライブラリの読み込み
        try:
            from youtubesearchpython import VideosSearch
            search = VideosSearch('ホルムズ海峡 情勢 解説', limit=1)
            result = search.result()
            if result and 'result' in result and len(result['result']) > 0:
                vid = result['result'][0]['id']
                v_title = result['result'][0]['title']
                record = Video.query.first()
                if not record:
                    db.session.add(Video(video_id=vid, title=v_title))
                else:
                    record.video_id = vid
                    record.title = v_title
                db.session.commit()
        except Exception as e:
            print(f"YouTube Update Error: {e}")

        # ニュース取得
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
                        # キーワードによる材料系カテゴリの自動分類
                        final_cat = base_cat
                        if any(kw in t_title for kw in ['ゴム', 'ホース', 'NBR', 'HNBR', 'タイヤ']):
                            final_cat = 'tire'
                        elif any(kw in t_title for kw in ['化学', 'プラント', 'ナフサ']):
                            final_cat = 'chemical'
                        
                        db.session.add(News(title=t_title, url=entry.link, category=final_cat, is_translated=True))
            db.session.commit()
        except Exception as e:
            print(f"News Update Error: {e}")

# --- サーバー起動時の初期化 ---
with app.app_context():
    # テーブル作成を確実に行う
    db.create_all()

# スケジュール設定
scheduler = BackgroundScheduler()
scheduler.add_job(func=fetch_and_save_data, trigger="interval", hours=1)
scheduler.start()

# 初回データをバックグラウンドで取得
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
    v_id = (Video.query.first().video_id if Video.query.first() else "r2Do5g2QzXk")
    return render_template('index.html', main_news=news, title="化学メーカー関連", video_id=v_id)

@app.route('/tire')
def tire():
    news = News.query.filter_by(category='tire').order_by(News.published_at.desc()).all()
    v_id = (Video.query.first().video_id if Video.query.first() else "r2Do5g2QzXk")
    return render_template('index.html', main_news=news, title="タイヤ・ホース関連", video_id=v_id)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
