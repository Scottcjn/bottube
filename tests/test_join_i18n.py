from bottube_server import app


def test_join_page_localizes_body_in_spanish():
    client = app.test_client()
    response = client.get('/join?lang=es')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'Únete a BoTTube' in html
    assert 'Para humanos' in html
    assert 'Crea una cuenta y empieza a subir videos directamente desde tu navegador.' in html
    assert 'Haz clic en' in html
    assert 'Registrarse' in html
    assert 'Three products, every package manager.' in html  # untouched section stays English
    assert 'For Humans' not in html
    assert 'Create an account and start uploading videos right from your browser.' not in html


def test_join_page_defaults_to_english_without_lang_override():
    client = app.test_client()
    response = client.get('/join')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'Join BoTTube' in html
    assert 'For Humans' in html
