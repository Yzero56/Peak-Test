Set-Location -LiteralPath 'C:\Users\PKNU-ICEE\Desktop\project'
Start-Process 'http://127.0.0.1:5004'
python browser_category_collector.py 192.168.4.1 --output category_collection_raw --port 5004
