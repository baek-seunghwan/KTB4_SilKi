package kr.ktb.silko_be.ai;

import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class MenuReindexRevisionRepository {
    private final JdbcClient jdbcClient;

    public MenuReindexRevisionRepository(JdbcClient jdbcClient) {
        this.jdbcClient = jdbcClient;
    }

    public long next(UUID storeId) {
        return jdbcClient.sql("""
                INSERT INTO menu_reindex_revisions (store_id, source_revision)
                VALUES (:storeId, 1)
                ON CONFLICT (store_id) DO UPDATE SET
                    source_revision = menu_reindex_revisions.source_revision + 1,
                    updated_at = now()
                RETURNING source_revision
                """)
            .param("storeId", storeId)
            .query(Long.class)
            .single();
    }
}
