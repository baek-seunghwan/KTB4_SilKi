package kr.ktb.silko_be.store;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.JoinTable;
import jakarta.persistence.ManyToMany;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import kr.ktb.silko_be.auth.AdminUser;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

@Entity
@Table(name = "stores")
public class Store {
    @Id
    private UUID id;

    @Column(nullable = false, length = 100)
    private String name;

    @Enumerated(EnumType.STRING)
    @Column(name = "operating_status", nullable = false)
    private OperatingStatus operatingStatus;

    @ManyToMany
    @JoinTable(name = "admin_stores",
        joinColumns = @JoinColumn(name = "store_id"),
        inverseJoinColumns = @JoinColumn(name = "admin_id"))
    private Set<AdminUser> admins = new HashSet<>();

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    protected Store() {}

    public Store(String name, AdminUser admin) {
        this(UUID.randomUUID(), name, admin);
    }

    public Store(UUID id, String name, AdminUser admin) {
        this.id = id;
        this.name = name;
        this.operatingStatus = OperatingStatus.OPEN;
        this.admins.add(admin);
    }

    public void changeStatus(OperatingStatus status) {
        this.operatingStatus = status;
    }

    public UUID getId() { return id; }
    public String getName() { return name; }
    public OperatingStatus getOperatingStatus() { return operatingStatus; }
}
