# ДЗ

1) Добиться 95% покрытия тестами вашей второй домашки - 1 балл

2) Настроить автозапуск этих тестов в CI, если вы подключали сторонюю БД, то можно посмотреть вот [сюда](https://dev.to/kashifsoofi/integration-test-postgres-using-github-actions-3lln), чтобы поддержать тесты с ней в CI. По итогу у вас должен получится зеленый пайплайн - оценивается в еще 2 балла.

отчет о покрытии:

pyton_backend on  hw-4-5 [!?] 
❯ docker compose -f hw45/docker-compose.yaml run --rm app pytest -q tests --cov=shop_api --cov-report=term-missing --
cov-fail-under=95
WARN[0000] /Users/lilclown/study/course2/pyton_backend/hw45/docker-compose.yaml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion 
[+] Creating 1/1
 ✔ Container hw45-db-1  Running                                                                                 0.0s 
.............................................                                                                 [100%]
================================================= warnings summary ==================================================
shop_api/main.py:651
  /app/shop_api/main.py:651: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    @app.on_event("startup")

../usr/local/lib/python3.12/site-packages/fastapi/applications.py:4575
  /usr/local/lib/python3.12/site-packages/fastapi/applications.py:4575: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    return self.router.on_event(event_type)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
================================================== tests coverage ===================================================
_________________________________ coverage: platform linux, python 3.12.12-final-0 __________________________________

Name                   Stmts   Miss  Cover   Missing
----------------------------------------------------
shop_api/__init__.py       0      0   100%
shop_api/main.py         356     11    97%   69-70, 174-175, 309, 320-322, 333, 617, 635
----------------------------------------------------
TOTAL                    356     11    97%
Required test coverage of 95% reached. Total coverage: 96.91%
45 passed, 2 warnings in 1.59s

pyton_backend on  hw-4-5 [!?] took 2s 

