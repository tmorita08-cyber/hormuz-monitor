from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
import feedparser
import urllib.parse
from datetime import datetime
import time
from deep_translator import GoogleTranslator

app = Flask(__name__)
# データベース設定
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///news.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- データベースモデル ---
class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    url = db.Column(db.String(500), unique=True, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    published_at = db.Column(db.DateTime, nullable=False)
    is_translated = db.Column(db.Boolean, default=False)

# --- 翻訳ヘルパー関数 ---
def translate_title(text):
    """英語が含まれる場合に日本語へ翻訳する"""
    try:
        # 英数字が一定以上含まれる場合に翻訳対象とする簡易判定
        if any(ord(char) < 128 for char in text):
            translated = GoogleTranslator(source='auto', target='ja').translate(text)
            return f"【翻訳】{translated}"
        return text
    except Exception as e:
        print(f"    翻訳エラー回避: {e}")
        return text

# --- ニュース収集コアロジック ---
def fetch_and_save_news():
    print(f"\n--- [{datetime.now()}] ニュース更新バッチ開始 ---")
    
    # カテゴリごとの日英検索キーワード
    queries = {
        'main': ['ホルムズ海峡', 'Strait of Hormuz'],
        'chemical': ['ホルムズ海峡 化学', 'Hormuz Chemical industry'],
        'tire_hose': ['ホルムズ海峡 タイヤ', 'Hormuz tire hose industry']
    }

    with app.app_context():
        for category, query_list in queries.items():
            print(f"\n[カテゴリ: {category}]")
            for query in query_list:
                print(f"  検索実行中: {query}...")
                encoded_query = urllib.parse.quote(query)
                # Google News RSS (言語設定を考慮しつつ取得)
                rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"
                feed = feedparser.parse(rss_url)
                
                new_count = 0
                for entry in feed.entries:
                    # URLで重複チェック
                    existing_news = News.query.filter_by(url=entry.link).first()
                    if not existing_news:
                        try:
                            # 日付パース
                            pub_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                            
                            # 英語記事なら翻訳（進捗をログ出し）
                            is_eng = any(ord(c) < 128 for c in entry.title[:20])
                            if is_eng:
                                print(f"    → 翻訳処理中: {entry.title[:40]}...")
                            
                            display_title = translate_title(entry.title)
                            
                            new_article = News(
                                title=display_title,
                                url=entry.link,
                                category=category,
                                published_at=pub_date,
                                is_translated=("【翻訳】" in display_title)
                            )
                            db.session.add(new_article)
                            new_count += 1
                        except Exception as e:
                            print(f"    記事保存エラー: {e}")
                
                db.session.commit()
                print(f"  完了: {new_count}件の新着記事を追加しました。")

    print(f"\n--- [{datetime.now()}] すべての更新が完了しました！ ---\n")

# --- 定期実行スケジュール (3時間おき) ---
scheduler = BackgroundScheduler()
scheduler.add_job(func=fetch_and_save_news, trigger="interval", hours=3)
scheduler.start()

# --- 共通データ取得ロジック ---
def get_news_by_category(category):
    filter_date = request.args.get('date')
    query = News.query.filter_by(category=category)
    if filter_date:
        # 日付フィルタリング
        query = query.filter(News.published_at.like(f"{filter_date}%"))
    return query.order_by(News.published_at.desc()).all()

# --- 画面ルーティング ---
@app.route('/')
def index():
    news_list = get_news_by_category('main')
    return render_template('index.html', title="主要ニュース（日英総合）", news=news_list, current_route='index')

@app.route('/chemical')
def chemical():
    news_list = get_news_by_category('chemical')
    return render_template('index.html', title="影響: 化学メーカー", news=news_list, current_route='chemical')

@app.route('/tire')
def tire():
    news_list = get_news_by_category('tire_hose')
    return render_template('index.html', title="影響: タイヤ・ホースメーカー", news=news_list, current_route='tire')

# --- 起動処理 ---
if __name__ == '__main__':
    with app.app_context():
        # 初回起動時にDB作成
        db.create_all()
        # 起動時に一度ニュースを取得
        fetch_and_save_news()
    
    # Webサーバー起動 (127.0.0.1:5000)
    app.run(debug=True, use_reloader=False)