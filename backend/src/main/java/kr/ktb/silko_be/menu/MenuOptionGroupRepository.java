package kr.ktb.silko_be.menu;

import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MenuOptionGroupRepository extends JpaRepository<MenuOptionGroup, UUID> {
    @EntityGraph(attributePaths = "values")
    List<MenuOptionGroup> findAllByMenu_IdInOrderByDisplayOrderAsc(Collection<UUID> menuIds);

    @EntityGraph(attributePaths = "values")
    List<MenuOptionGroup> findAllByMenu_IdOrderByDisplayOrderAsc(UUID menuId);
}
