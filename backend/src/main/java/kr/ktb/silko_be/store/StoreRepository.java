package kr.ktb.silko_be.store;

import jakarta.persistence.LockModeType;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface StoreRepository extends JpaRepository<Store, UUID> {
    @Query("select distinct s from Store s join s.admins a where a.email = :email order by s.createdAt")
    List<Store> findAllManagedBy(@Param("email") String email);

    @Query("select s from Store s join s.admins a where s.id = :id and a.email = :email")
    Optional<Store> findManagedById(@Param("id") UUID id, @Param("email") String email);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select s from Store s where s.id = :id")
    Optional<Store> findByIdForUpdate(@Param("id") UUID id);
}
