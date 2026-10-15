(function () {
  function categoryPath(value) {
    const values = Array.isArray(value) ? value : [value];
    return values
      .flatMap((item) => typeof item === "string" ? item.split(" / ") : [])
      .map((item) => item.trim())
      .filter(Boolean);
  }

  let siteConfigurationRequest;

  function loadSiteConfiguration() {
    if (!siteConfigurationRequest) {
      siteConfigurationRequest = fetch("/data/site.json", { cache: "no-store" })
        .then((response) => {
          if (!response.ok) throw new Error("Configurazione sito non disponibile.");
          return response.json();
        })
        .catch((error) => {
          siteConfigurationRequest = null;
          throw error;
        });
    }
    return siteConfigurationRequest;
  }

  function configuredProfiles(site) {
    const profiles = Array.isArray(site.profiles) ? site.profiles : [];
    return profiles
      .filter((profile) => profile && typeof profile.value === "string" && profile.value.trim()
        && typeof profile.label === "string" && profile.label.trim())
      .map((profile) => ({ value: profile.value.trim(), label: profile.label.trim() }));
  }

  const CategoryControl = createClass({
    getInitialState: function () {
      return { categories: [], loading: true, error: "" };
    },

    componentDidMount: function () {
      loadSiteConfiguration()
        .then((site) => {
          const categories = Array.isArray(site.categories)
            ? site.categories.filter((category) => category && typeof category === "object" && typeof category.name === "string" && category.name.trim())
            : [];
          this.setState({ categories, loading: false });
        })
        .catch(() => this.setState({ loading: false, error: "Impossibile caricare le categorie da site.json." }));
    },

    handleChange: function (depth, event) {
      const path = categoryPath(this.props.value).slice(0, depth);
      const value = event.target.value.trim();
      if (value) path.push(value);
      this.props.onChange(path);
    },

    render: function () {
      const currentPath = categoryPath(this.props.value);
      const controls = [];
      let categories = this.state.categories;

      for (let depth = 0; categories.length > 0; depth += 1) {
        const value = currentPath[depth] || "";
        const selectedCategory = categories.find((category) => category.name === value);
        controls.push(h("label", { key: `category-level-${depth}` }, [
          h("span", {}, depth === 0 ? "Categoria" : `Sottocategoria ${depth}`),
          h("select", {
            id: depth === 0 ? this.props.forID : undefined,
            className: depth === 0 ? this.props.classNameWrapper : undefined,
            value: selectedCategory ? value : "",
            onChange: (event) => this.handleChange(depth, event),
          }, [
            h("option", { value: "" }, depth === 0 ? "Seleziona categoria" : "Categoria principale"),
            ...categories.map((category) => h("option", { key: category.name, value: category.name }, category.name)),
          ]),
        ]));

        if (!selectedCategory) break;
        categories = Array.isArray(selectedCategory.children) ? selectedCategory.children : [];
      }

      return h("div", {}, [
        this.state.error ? h("p", { role: "alert" }, this.state.error) : null,
        this.state.loading ? h("p", {}, "Caricamento categorie…") : null,
        ...controls,
      ]);
    },
  });

  const CategoryPreview = createClass({
    render: function () {
      return h("span", {}, categoryPath(this.props.value).join(" / ") || "Nessuna categoria");
    },
  });

  const ProfileControl = createClass({
    getInitialState: function () {
      return { profiles: [], loading: true, error: "" };
    },

    componentDidMount: function () {
      loadSiteConfiguration()
        .then((site) => this.setState({ profiles: configuredProfiles(site), loading: false }))
        .catch(() => this.setState({ loading: false, error: "Impossibile caricare le attività da site.json." }));
    },

    handleChange: function (event) {
      this.props.onChange(event.target.value);
    },

    render: function () {
      const value = typeof this.props.value === "string" ? this.props.value : "";
      const profiles = [...this.state.profiles];
      if (value && !profiles.some((profile) => profile.value === value)) {
        profiles.push({ value, label: value });
      }

      return h("div", {}, [
        this.state.error ? h("p", { role: "alert" }, this.state.error) : null,
        this.state.loading ? h("p", {}, "Caricamento attività…") : null,
        h("select", {
          id: this.props.forID,
          className: this.props.classNameWrapper,
          value,
          onChange: this.handleChange,
        }, [
          h("option", { value: "" }, "Seleziona attività"),
          ...profiles.map((profile) => h("option", { key: profile.value, value: profile.value }, profile.label)),
        ]),
      ]);
    },
  });

  const ProfilePreview = createClass({
    getInitialState: function () {
      return { profiles: [] };
    },

    componentDidMount: function () {
      loadSiteConfiguration()
        .then((site) => this.setState({ profiles: configuredProfiles(site) }))
        .catch(() => {});
    },

    render: function () {
      const value = typeof this.props.value === "string" ? this.props.value : "";
      const profile = this.state.profiles.find((item) => item.value === value);
      return h("span", {}, profile?.label || value || "Nessuna attività");
    },
  });

  CMS.registerWidget("category-list", CategoryControl, CategoryPreview);
  CMS.registerWidget("profile-select", ProfileControl, ProfilePreview);
})();