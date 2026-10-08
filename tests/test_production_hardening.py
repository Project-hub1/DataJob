def test_health_endpoint(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json['status'] == 'ok'

def test_readiness_endpoint(client):
    response = client.get('/health/ready')
    assert response.status_code == 200
    assert response.json['database'] == 'ok'

def test_security_headers(client):
    response = client.get('/')
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'SAMEORIGIN'
    assert 'Content-Security-Policy' in response.headers
    assert 'X-Request-ID' in response.headers

def test_auth_pages_have_password_toggle_controls(client):
    for path in ['/login', '/register', '/forgot-password']:
        response = client.get(path)
        assert response.status_code == 200
    login = client.get('/login').data.decode()
    register = client.get('/register').data.decode()
    assert 'data-password-toggle="login-password"' in login
    assert 'data-password-toggle="register-password"' in register

