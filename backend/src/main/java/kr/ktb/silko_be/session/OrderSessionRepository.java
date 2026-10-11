package kr.ktb.silko_be.session;

import java.util.UUID;
import java.util.Optional;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import jakarta.persistence.LockModeType;

public interface OrderSessionRepository extends JpaRepository<OrderSession, UUID> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select session from OrderSession session where session.id = :id")
    Optional<OrderSession> findByIdForUpdate(@Param("id") UUID id);
}
