// Bloom (calm): petals fade in one by one around a center until the flower is whole at 100%.
// No movement at all, only gentle fades. Shown when the device has "Reduce motion" turned on.
const PETALS = 12;

export default {
  id: "bloom",
  calm: true,
  create({ THREE, scene, colors }) {
    const petalGeometry = new THREE.SphereGeometry(0.5, 16, 12);
    const petals = [];
    for (let i = 0; i < PETALS; i++) {
      const angle = Math.PI / 2 - (i / PETALS) * Math.PI * 2;   // from the top, clockwise
      const material = new THREE.MeshStandardMaterial({ color: i % 2 ? colors.hot : colors.third, roughness: 0.5, transparent: true, opacity: 0 });
      const petal = new THREE.Mesh(petalGeometry, material);
      petal.scale.set(1.7, 0.62, 0.4);
      petal.position.set(Math.cos(angle) * 1.55, Math.sin(angle) * 1.55, 0);
      petal.rotation.z = angle;
      scene.add(petal);
      petals.push(petal);
    }
    const center = new THREE.Mesh(new THREE.SphereGeometry(0.8, 24, 16), new THREE.MeshStandardMaterial({ color: colors.ink, roughness: 0.5 }));
    scene.add(center);

    return {
      update(state) {
        const shown = state.progress * PETALS;
        const settle = Math.min(1, state.ended);
        petals.forEach((petal, i) => {
          const opacity = Math.min(1, Math.max(0, shown - i));
          petal.material.opacity = state.status === "failed" ? opacity * (1 - 0.6 * settle) : opacity;
        });
        if (state.status === "done") center.material.color.lerpColors(colors.ink, colors.zap, settle);
        if (state.status === "failed") center.material.color.lerpColors(colors.ink, colors.muted, settle);
      },
    };
  },
};
