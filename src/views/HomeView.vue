<template>
  <section class="surface-card home-page">
    <div class="hero">
      <h1>Planowanie diety dla calej rodziny</h1>
      <p>
        Tworz harmonogram posilkow, korzystaj ze wspolnego katalogu przepisow i generuj liste zakupow
        gotowa do sklepu.
      </p>
    </div>

    <div class="feature-grid">
      <RouterLink to="/catalog" class="feature-card">
        <h2>Katalog</h2>
        <p>Przegladaj produkty i przepisy. Dane zaimportowane z PDF sa publiczne i tylko do odczytu.</p>
      </RouterLink>

      <RouterLink to="/ingredients" class="feature-card">
        <h2>Skladniki</h2>
        <p>Zarzadzaj lista skladnikow oraz ich parametrami odzywczymi (wymaga uprawnien).</p>
      </RouterLink>

      <RouterLink to="/settings" class="feature-card">
        <h2>Ustawienia</h2>
        <p>Jednostki, tagi, preferencje interfejsu oraz konfiguracja konta.</p>
      </RouterLink>
    </div>
  </section>
</template>

<script setup>
import { RouterLink } from 'vue-router'
</script>

<style scoped>
.home-page {
  display: grid;
  gap: 1rem;
}

.hero {
  display: grid;
  gap: 0.6rem;
}

.hero p {
  color: var(--app-muted);
  max-width: 70ch;
}

.feature-grid {
  display: grid;
  gap: 0.9rem;
}

.feature-card {
  border: 1px solid var(--app-border);
  border-radius: 0.8rem;
  padding: 0.85rem;
  background: var(--app-surface-alt);
  color: var(--app-text);
  text-decoration: none;
}

.feature-card p {
  margin-top: 0.35rem;
  color: var(--app-muted);
}

@media (min-width: 900px) {
  .feature-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
