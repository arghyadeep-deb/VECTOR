<!-- VECTOR-INGESTED ASSET
  Source: C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\sickn33_antigravity-awesome-skills\repo\skills\avalonia-viewmodels-zafiro\navigation_sections.md
  Personalized for VECTOR runtime — local Ollama, no paid APIs.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T01:39:46+00:00
-->

# Navigation & Sections

Zafiro provides powerful abstractions for managing application-wide navigation and modular UI sections.

## Navigation with INavigator

The `INavigator` interface is used to switch between different views or viewmodels.

```csharp
public class MyViewModel(INavigator navigator)
{
    public async Task GoToDetails()
    {
        await navigator.Navigate(() => new DetailsViewModel());
    }
}
```

## UI Sections

Sections are modular parts of the UI (like tabs or sidebar items) that can be automatically registered.

### The [Section] Attribute

ViewModels intended to be sections should be marked with the `[Section]` attribute.

```csharp
[Section("Wallet", icon: "fa-wallet")]
public class WalletSectionViewModel : IWalletSectionViewModel
{
    // ...
}
```

### Automatic Registration

In the `CompositionRoot`, sections can be automatically registered:

```csharp
services.AddAnnotatedSections(logger);
services.AddSectionsFromAttributes(logger);
```

### Switching Sections

You can switch the current active section via the `IShellViewModel`:

```csharp
shellViewModel.SetSection("Browse");
```

> [!IMPORTANT]
> The `icon` parameter in the `[Section]` attribute supports FontAwesome icons (e.g., `fa-home`) when configured with `ProjektankerIconControlProvider`.
