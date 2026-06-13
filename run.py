from app import app
from database import init_db
import os

if __name__ == '__main__':
    init_db(app)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
