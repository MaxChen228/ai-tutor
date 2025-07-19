-- 知識點向量化與自動關聯功能的資料庫遷移腳本
-- 執行前請確保已安裝 pgvector 擴展

-- 1. 啟用 pgvector 擴展（如果尚未啟用）
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. 為 knowledge_points 表新增 embedding_vector 欄位
-- 使用 384 維向量（適用於 MiniLM 模型）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='knowledge_points' AND column_name='embedding_vector'
    ) THEN
        ALTER TABLE knowledge_points ADD COLUMN embedding_vector vector(384);
        RAISE NOTICE '欄位 embedding_vector 已成功加入 knowledge_points 表格。';
    ELSE
        RAISE NOTICE '欄位 embedding_vector 已存在於 knowledge_points 表格中。';
    END IF;
END $$;

-- 3. 新增向量更新時間欄位
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='knowledge_points' AND column_name='embedding_updated_at'
    ) THEN
        ALTER TABLE knowledge_points ADD COLUMN embedding_updated_at TIMESTAMPTZ;
        RAISE NOTICE '欄位 embedding_updated_at 已成功加入 knowledge_points 表格。';
    ELSE
        RAISE NOTICE '欄位 embedding_updated_at 已存在於 knowledge_points 表格中。';
    END IF;
END $$;

-- 4. 建立 knowledge_links 表格儲存知識點間的關聯關係
CREATE TABLE IF NOT EXISTS knowledge_links (
    id SERIAL PRIMARY KEY,
    source_point_id INTEGER REFERENCES knowledge_points(id) ON DELETE CASCADE,
    target_point_id INTEGER REFERENCES knowledge_points(id) ON DELETE CASCADE,
    similarity_score REAL NOT NULL CHECK (similarity_score >= 0 AND similarity_score <= 1),
    link_type TEXT DEFAULT 'semantic_similarity' CHECK (link_type IN ('semantic_similarity', 'manual_link', 'category_based')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    
    -- 確保不會有重複的關聯和自我關聯
    UNIQUE(source_point_id, target_point_id),
    CHECK(source_point_id != target_point_id)
);

-- 5. 建立索引優化查詢效能
-- 向量相似度搜尋索引（HNSW 演算法，適合高維向量）
CREATE INDEX IF NOT EXISTS idx_knowledge_points_embedding_hnsw 
ON knowledge_points USING hnsw (embedding_vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- 傳統索引
CREATE INDEX IF NOT EXISTS idx_knowledge_points_embedding_updated 
ON knowledge_points(embedding_updated_at) 
WHERE embedding_vector IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_knowledge_links_source_point 
ON knowledge_links(source_point_id, similarity_score DESC);

CREATE INDEX IF NOT EXISTS idx_knowledge_links_target_point 
ON knowledge_links(target_point_id, similarity_score DESC);

CREATE INDEX IF NOT EXISTS idx_knowledge_links_active_links 
ON knowledge_links(is_active, similarity_score DESC) 
WHERE is_active = TRUE;

-- 6. 建立用於向量搜尋的便利函數
CREATE OR REPLACE FUNCTION find_similar_knowledge_points(
    target_vector vector(384),
    similarity_threshold REAL DEFAULT 0.75,
    max_results INTEGER DEFAULT 10,
    exclude_point_id INTEGER DEFAULT NULL
)
RETURNS TABLE (
    point_id INTEGER,
    similarity_score REAL,
    correct_phrase TEXT,
    key_point_summary TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        kp.id,
        1 - (kp.embedding_vector <=> target_vector) AS similarity,
        kp.correct_phrase,
        kp.key_point_summary
    FROM knowledge_points kp
    WHERE kp.embedding_vector IS NOT NULL
        AND kp.is_archived = FALSE
        AND (exclude_point_id IS NULL OR kp.id != exclude_point_id)
        AND (1 - (kp.embedding_vector <=> target_vector)) >= similarity_threshold
    ORDER BY kp.embedding_vector <=> target_vector
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;

-- 7. 建立批次更新向量的便利函數
CREATE OR REPLACE FUNCTION update_knowledge_point_embedding(
    point_id INTEGER,
    new_vector vector(384)
)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE knowledge_points 
    SET embedding_vector = new_vector,
        embedding_updated_at = NOW()
    WHERE id = point_id;
    
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- 8. 建立清理無效關聯的函數
CREATE OR REPLACE FUNCTION cleanup_invalid_links()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    -- 刪除指向已封存知識點的關聯
    DELETE FROM knowledge_links 
    WHERE source_point_id IN (
        SELECT id FROM knowledge_points WHERE is_archived = TRUE
    ) OR target_point_id IN (
        SELECT id FROM knowledge_points WHERE is_archived = TRUE
    );
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- 9. 建立統計資訊視圖
CREATE OR REPLACE VIEW knowledge_linking_stats AS
SELECT 
    (SELECT COUNT(*) FROM knowledge_points WHERE embedding_vector IS NOT NULL) as points_with_vectors,
    (SELECT COUNT(*) FROM knowledge_points WHERE embedding_vector IS NULL AND is_archived = FALSE) as points_without_vectors,
    (SELECT COUNT(*) FROM knowledge_links WHERE is_active = TRUE) as active_links,
    (SELECT AVG(similarity_score) FROM knowledge_links WHERE is_active = TRUE) as avg_similarity_score,
    (SELECT MAX(embedding_updated_at) FROM knowledge_points) as last_embedding_update;

-- 完成訊息
DO $$
BEGIN
    RAISE NOTICE '=== 知識點向量化與自動關聯功能資料庫遷移完成 ===';
    RAISE NOTICE '1. ✅ pgvector 擴展已啟用';
    RAISE NOTICE '2. ✅ knowledge_points 表格已新增 embedding_vector 欄位';
    RAISE NOTICE '3. ✅ knowledge_links 表格已建立';
    RAISE NOTICE '4. ✅ 相關索引已建立完成';
    RAISE NOTICE '5. ✅ 便利函數已建立完成';
    RAISE NOTICE '請執行 Python 腳本開始生成現有知識點的向量';
END $$;