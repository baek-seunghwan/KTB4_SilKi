package kr.ktb.silko_be.order;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface OrderRepository extends JpaRepository<CustomerOrder, UUID> {
    @EntityGraph(attributePaths = "items")
    Optional<CustomerOrder> findByStoreIdAndIdempotencyKey(UUID storeId, String idempotencyKey);

    @EntityGraph(attributePaths = "items")
    Optional<CustomerOrder> findByOrderSessionId(UUID orderSessionId);

    @EntityGraph(attributePaths = "items")
    Optional<CustomerOrder> findByIdAndStoreId(UUID id, UUID storeId);

    @Override
    @EntityGraph(attributePaths = "items")
    Optional<CustomerOrder> findById(UUID id);

    @Query(value = """
        SELECT * FROM orders
        WHERE store_id = :storeId AND status IN (:statuses)
        ORDER BY CASE status
            WHEN 'RECEIVED' THEN 0
            WHEN 'PREPARING' THEN 1
            ELSE 2
        END, created_at DESC
        """,
        countQuery = "SELECT count(*) FROM orders WHERE store_id = :storeId AND status IN (:statuses)",
        nativeQuery = true)
    Page<CustomerOrder> findAllByStoreIdAndStatusInWorkflowOrder(
        @Param("storeId") UUID storeId, @Param("statuses") java.util.List<String> statuses, Pageable pageable);

    @Query(value = """
        SELECT * FROM orders
        WHERE store_id = :storeId
        ORDER BY CASE status
            WHEN 'RECEIVED' THEN 0
            WHEN 'PREPARING' THEN 1
            ELSE 2
        END, created_at DESC
        """,
        countQuery = "SELECT count(*) FROM orders WHERE store_id = :storeId",
        nativeQuery = true)
    Page<CustomerOrder> findAllByStoreIdInWorkflowOrder(@Param("storeId") UUID storeId, Pageable pageable);

    @Query(value = "select nextval('order_number_seq')", nativeQuery = true)
    long nextOrderNumber();
}
