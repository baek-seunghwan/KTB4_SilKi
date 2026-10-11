package kr.ktb.silko_be.menu;

import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MenuRepository extends JpaRepository<Menu, UUID> {
    Page<Menu> findAllByStoreIdAndCategory(UUID storeId, MenuCategory category, Pageable pageable);
    Optional<Menu> findByIdAndStoreId(UUID id, UUID storeId);
    List<Menu> findAllByStoreIdAndIdIn(UUID storeId, Collection<UUID> ids);
}
