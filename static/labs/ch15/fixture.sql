INSERT INTO shop_ch15.fixture_meta (
    fixture_version,
    corpus_identity,
    query_identity,
    judgment_identity,
    embedding_model,
    embedding_method,
    text_license,
    vector_license,
    frozen_at
)
VALUES (
    'ch15-search-v1',
    'frozen-corpus.csv',
    'frozen-queries.csv',
    'frozen-judgments.csv',
    'pg36-handcrafted-topic-4d-v1',
    'manually assigned deterministic topic coordinates',
    'project-owned synthetic fixture; repository terms apply',
    'handcrafted numeric fixture; no external model license',
    TIMESTAMPTZ '2026-07-29 00:00:00+00'
);

INSERT INTO shop_ch15.product_search (
    product_id,
    sku,
    category,
    active,
    title,
    description,
    embedding,
    embedding_model
)
VALUES
    (
        1,
        'AUD-001',
        'audio',
        true,
        'Wireless Noise-Canceling Headphones',
        'Over-ear headphones for focused listening during travel.',
        '[1,0,0,0]',
        'pg36-handcrafted-topic-4d-v1'
    ),
    (
        2,
        'AUD-002',
        'audio',
        true,
        'Portable Bluetooth Speaker',
        'Compact speaker for music on the go with a twelve-hour battery.',
        '[0.9,0,0,0]',
        'pg36-handcrafted-topic-4d-v1'
    ),
    (
        3,
        'AUD-003',
        'audio',
        true,
        'Wired Studio Headphones',
        'Reference headphones for recording and mixing.',
        '[0.84,0,0,0]',
        'pg36-handcrafted-topic-4d-v1'
    ),
    (
        4,
        'KIT-001',
        'kitchen',
        true,
        'Burr Coffee Grinder',
        'Conical burr grinder for fresh coffee beans and adjustable grind size.',
        '[0,1,0,0]',
        'pg36-handcrafted-topic-4d-v1'
    ),
    (
        5,
        'KIT-002',
        'kitchen',
        true,
        'Home Espresso Machine',
        'Compact machine for making espresso and steaming milk at home.',
        '[0,0.9,0,0]',
        'pg36-handcrafted-topic-4d-v1'
    ),
    (
        6,
        'KIT-003',
        'kitchen',
        true,
        'Pour-Over Coffee Maker',
        'Manual brewer for clean coffee with a reusable filter.',
        '[0,0.82,0,0]',
        'pg36-handcrafted-topic-4d-v1'
    ),
    (
        7,
        'OUT-001',
        'outdoor',
        true,
        'Insulated Trail Water Bottle',
        'Steel bottle for cold trail hydration on long hikes.',
        '[0,0,1,0]',
        'pg36-handcrafted-topic-4d-v1'
    ),
    (
        8,
        'OUT-002',
        'outdoor',
        true,
        'Lightweight Hiking Backpack',
        'Twenty-liter trail pack with a hydration sleeve.',
        '[0,0,0.9,0]',
        'pg36-handcrafted-topic-4d-v1'
    ),
    (
        9,
        'OUT-003',
        'outdoor',
        true,
        'Camping Water Filter',
        'Portable filter for safe water during backcountry trips.',
        '[0,0,0.84,0]',
        'pg36-handcrafted-topic-4d-v1'
    ),
    (
        10,
        'BOK-001',
        'books',
        true,
        'PostgreSQL Administration Handbook',
        'Operations guide for backup recovery replication and database tuning.',
        '[0,0,0,1]',
        'pg36-handcrafted-topic-4d-v1'
    ),
    (
        11,
        'BOK-002',
        'books',
        true,
        'Database Performance Course',
        'Hands-on PostgreSQL query planning indexing and database tuning.',
        '[0,0,0,0.9]',
        'pg36-handcrafted-topic-4d-v1'
    ),
    (
        12,
        'BOK-003',
        'books',
        true,
        'Vector Search Engineering Guide',
        'Practical semantic nearest-neighbor retrieval with embeddings and PostgreSQL.',
        '[0.25,0,0,0.82]',
        'pg36-handcrafted-topic-4d-v1'
    ),
    (
        13,
        'AUD-004',
        'audio',
        true,
        'USB-C Audio Adapter',
        'Compact adapter for wired headphones and mobile devices.',
        '[0.55,0,0,0]',
        'pg36-handcrafted-topic-4d-v1'
    ),
    (
        14,
        'KIT-004',
        'kitchen',
        true,
        'Digital Coffee Scale',
        'Compact scale for repeatable coffee brewing.',
        '[0,0.6,0,0]',
        'pg36-handcrafted-topic-4d-v1'
    ),
    (
        15,
        'OUT-004',
        'outdoor',
        true,
        'Merino Hiking Socks',
        'Lightweight socks for long trail days.',
        '[0,0,0.55,0]',
        'pg36-handcrafted-topic-4d-v1'
    ),
    (
        16,
        'BOK-004',
        'books',
        true,
        'SQL Pocket Reference',
        'Compact reference for SQL syntax and common queries.',
        '[0,0,0,0.55]',
        'pg36-handcrafted-topic-4d-v1'
    ),
    (
        17,
        'AUD-005',
        'audio',
        false,
        'Legacy Wireless Earbuds',
        'Discontinued wireless earbuds retained for active-filter tests.',
        '[0.95,0,0,0]',
        'pg36-handcrafted-topic-4d-v1'
    );

INSERT INTO shop_ch15.eval_query (
    query_id,
    raw_query,
    category_filter,
    embedding,
    embedding_model,
    intent
)
VALUES
    (
        'q01',
        'wireless headphones',
        'audio',
        '[0.9,0,0,0]',
        'pg36-handcrafted-topic-4d-v1',
        'exact product words'
    ),
    (
        'q02',
        'wireles hedphones',
        'audio',
        '[0.9,0,0,0]',
        'pg36-handcrafted-topic-4d-v1',
        'two spelling errors'
    ),
    (
        'q03',
        'music on the go',
        'audio',
        '[0.9,0,0,0]',
        'pg36-handcrafted-topic-4d-v1',
        'descriptive audio intent'
    ),
    (
        'q04',
        'coffee bean grinder',
        'kitchen',
        '[0,0.9,0,0]',
        'pg36-handcrafted-topic-4d-v1',
        'exact product and ingredient'
    ),
    (
        'q05',
        'make espresso at home',
        'kitchen',
        '[0,0.9,0,0]',
        'pg36-handcrafted-topic-4d-v1',
        'descriptive kitchen intent'
    ),
    (
        'q06',
        'trail hydration',
        'outdoor',
        '[0,0,0.9,0]',
        'pg36-handcrafted-topic-4d-v1',
        'cross-title description terms'
    ),
    (
        'q07',
        'postgre databse tuning',
        'books',
        '[0,0,0,0.9]',
        'pg36-handcrafted-topic-4d-v1',
        'database intent with spelling errors'
    ),
    (
        'q08',
        'semantic nearest neighbor',
        'books',
        '[0.25,0,0,0.82]',
        'pg36-handcrafted-topic-4d-v1',
        'semantic retrieval terminology'
    );

INSERT INTO shop_ch15.relevance_judgment (
    query_id,
    product_id,
    grade,
    rationale
)
VALUES
    ('q01', 1, 3, 'wireless headphones are the exact intent'),
    ('q01', 3, 2, 'wired headphones satisfy the product class'),
    ('q01', 2, 1, 'portable speaker is related audio equipment'),
    ('q02', 1, 3, 'typo-corrected exact intent'),
    ('q02', 3, 2, 'headphone class remains relevant'),
    ('q02', 2, 1, 'related audio fallback'),
    ('q03', 2, 3, 'portable speaker best matches mobile music'),
    ('q03', 1, 2, 'travel headphones also match mobile music'),
    ('q03', 3, 1, 'studio headphones are weaker for mobility'),
    ('q04', 4, 3, 'grinder exactly matches coffee beans'),
    ('q04', 5, 1, 'espresso workflow often needs a grinder'),
    ('q04', 6, 1, 'pour-over workflow also needs ground coffee'),
    ('q05', 5, 3, 'espresso machine is the exact task'),
    ('q05', 4, 2, 'grinder is important to espresso preparation'),
    ('q05', 6, 1, 'another home coffee preparation method'),
    ('q06', 7, 3, 'water bottle exactly serves trail hydration'),
    ('q06', 8, 2, 'backpack includes a hydration sleeve'),
    ('q06', 9, 1, 'water filter supports backcountry hydration'),
    ('q07', 10, 3, 'administration handbook covers database tuning'),
    ('q07', 11, 2, 'performance course covers PostgreSQL tuning'),
    ('q07', 12, 1, 'vector search guide is a PostgreSQL engineering book'),
    ('q08', 12, 3, 'guide exactly covers semantic nearest-neighbor retrieval'),
    ('q08', 11, 1, 'database performance is adjacent engineering material'),
    ('q08', 10, 1, 'PostgreSQL administration is adjacent reference material');
