"""Rekonstruierter Einstiegspunkt fuer die unveraendert extrahierten Module.

Der originale Import-Loader fuer eingebettete Module wird bei dieser
Ordnerstruktur nicht benoetigt. Dieser Starter ist neu erstellt.
"""
if __name__ == '__main__':
    from server import main
    main()
