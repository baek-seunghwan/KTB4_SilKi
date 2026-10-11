package kr.ktb.silko_be.cart;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CartItemRepository extends JpaRepository<CartItem, UUID> {
    @EntityGraph(attributePaths = {"menu", "selectedOptions", "selectedOptions.optionGroup"})
    List<CartItem> findAllByOrderSession_IdOrderByCreatedAtAsc(UUID sessionId);

    @EntityGraph(attributePaths = {"menu", "selectedOptions", "selectedOptions.optionGroup"})
    Optional<CartItem> findByIdAndOrderSession_Id(UUID id, UUID sessionId);
}
