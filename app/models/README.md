# Models

`app.models`를 import하면 Alembic이 인식할 모든 SQLAlchemy 모델이 등록된다.

모델의 테이블 생성과 변경은 `Base.metadata.create_all()` 대신 Alembic migration으로 관리한다.
