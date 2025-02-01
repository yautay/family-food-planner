<template>
  <div class="home">
    <h1>Planowanie zakupów</h1>
    <router-link to="/ingredients">
      <button>Go to Ingredients</button>
    </router-link>
    <router-link to="/meals">
      <button>Go to Meals</button>
    </router-link>
    <router-link to="/settings">
      <button>Go to Settings</button>
    </router-link>
  </div>
</template>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

button {
  padding: 0.5rem 1rem;
  font-size: 1rem;
  cursor: pointer;
}
</style>
