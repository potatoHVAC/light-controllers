from server.serverlog import ServerLog


def test_server_and_mesh_are_separate_buffers():
    log = ServerLog()
    for i in range(5):
        log.write(f'server msg {i}', source='server')
    for i in range(10):
        log.write(f'mesh msg {i}', source='mesh')
    assert len(log.entries(source='server')) == 5
    assert len(log.entries(source='mesh')) == 10


def test_mesh_flood_does_not_evict_server_entries():
    log = ServerLog()
    log.write('important server event', source='server')
    for i in range(300):
        log.write(f'mesh noise {i}', source='mesh')
    server = log.entries(source='server')
    assert any('important server event' in e['msg'] for e in server)


def test_entries_limit_respected():
    log = ServerLog()
    for i in range(50):
        log.write(f'msg {i}', source='server')
    assert len(log.entries(limit=10, source='server')) == 10


def test_level_stored_as_type():
    log = ServerLog()
    log.write('ok msg', level='ok', source='server')
    log.write('warn msg', level='warn', source='mesh')
    assert log.entries(source='server')[-1]['type'] == 'ok'
    assert log.entries(source='mesh')[-1]['type'] == 'warn'