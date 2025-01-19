Napomena: oznake označene sa *italic* su novo dodane, oznake koje su **podebljane** su implementirane

------

Naziv projekta: ParkMan

Članovi tima: Damjan Đekić, Benjamin Jakupović

Aplikacija se sastoji od 3 dijela:

·        Web app za voditelja

·        Mobile app za osobu koja parkira

·        API za senzore

Dva tipa korisnika će koristiti aplikaciju: voditelj, osoba koja parkira

# Faza1:

Aplikacija će biti skalabilna te se sastojati od web servera, loadbalancera, NoSQL baze za voditelja, parkove i njihova parking mjesta te NoSQL baze koja zapisuje trenutna stanja parkinga. Dodaje se i API koji će simulirati mobilnu aplikaciju.

*Također će postojati i SQL baza koja sprema transakcijske podatke te pomoću njih računa trajanje parkinga i određuje cijenu.*

 

Implementira web aplikaciju za voditelja:

·        Ima pristup web aplikaciji u kojoj se definiraju parkovi za parking **(samo simulirano s pozivima API-a)**

·        **može definirati nove parkove za parking (njihovu lokaciju u svijetu, naziv) i za tu lokaciju definirati koliko mjesta postoji, i definirati cijenu za to parking mjesto (po defaultu su cijene za sva mjesta jednaka).**

Funkcionalnosti ovog dijela aplikacije će biti simulirane API pozivima, kojima se prosljeđuje odgovarajući JSON dokument u zahtjevu.

 

„Implementira“ mobilnu aplikaciju za osobu koja parkira (mobilna aplikacija simulirana sa API pozivima):

·        **Vide listu parkinga svih voditelja te mogu izabrati parking po nazivu** ili se izabere onaj najbliži njihovoj GPS lokaciji

·        **Korisnik stvara account za aplikaciju (definira ime, prezime, registracijske oznake auta i "kućnu lokaciju")**

·        Za svaki parking vide trenutno stanje (koliko slobodnih mjesta) *(nije implementirano u ovoj fazi)*

·        **Imaju pristup rampi. Pomoću aplikacije (ako su u blizini rampe), zatraže parking, dodaje se njihov zapis u bazu (timestamp)**, primaju svoj kod i baza se otvara *(postupak dodavanja koda nije potpuno implementiran - ovisi o mobilnoj aplikaciji)*

·        Prilikom dolaska do mjesta za izlaz, skeniraju svoj kod s mobitela, brišu se iz baze te se računa cijena koju je potrebno platiti

·        Mogu imati aktivan samo jedan kod za parking, koji im se briše čim izađu iz parka

 

 

 

 

 

# Faza 2:

Proširenje faze 1, dodaje se SQL baza, koja se koristi za analitiku. Također se dodaju nove funkcionalnosti za voditelja te izvodi batch processing za podatke o parkingu.

 

·        Voditelj ima pristup dashboardu

·        na dashboardu se za izabrani park za parking može vidjeti zarada (po vremenu - dan, mjesec, godina), trenutna zauzetost parkinga te kretanje zauzetosti kroz vrijeme (peak hours) za prethodne dane (otkako je parking otvoren)

·        batch processing na kraju tjedna izračunava kumulativno stanje parkinga (zarada, avg peag hour)

 

Dodaje se API za senzore koji ažuriraju stanja parking mjesta:

·        Oprema parkinga uključuje kamere, rampe i senzore za mjesta + tabla za zauzetost parkinga (koja prikazuje status - slobodno/zauzeto)

·        Imaju pristup API-u koji ažurira/dobiva podatke o stanju parkinga - kada je osoba parkirala, koje mjesto je slobodno, ima li slobodnih mjesta, koliko dugo je osoba parkirana i druge info koje su potrebne kako bi se izračunala cijena parkinga kada osoba izlazi iz parka

·        Rampa treba imati kameru (OCR, faza 4). Svako parking mjesto treba imati kameru i senzor zauzetosti (faza 5).

 

 

 

Faza3:

Monitoring za praćenje stanja dijelova aplikacije.

Optimizacija baze koja prati zauzetost parkinga uvođenjem cachinga. Caching će se koristiti za brz pristup popisu koji prikazuje trenutno stanje parkinga.

 

Faza 4:

OCR za tablice, gdje se može prepoznati/otkriti registracijski broj auta.

Voditelj:

·        Voditelj dodaje stanovnika u bazu

Osoba koja parkira:

·        Osoba može kontaktirati voditelja za pravo stanovnika, voditelj može zahtjev odobriti/odbiti

·        Prilikom izrade korisničkog računa, korisnik dodaje registracijsku oznaku svojeg auta/svojih autiju i definira je li invalid

 

 

Oprema parkinga:

·        Kamera na rampi slika tablice auta koje dolaze - ako registracija odgovara registraciji stanovnika, rampa za ulaz se otvara automatski. Ista situacija je i prilikom izlaska iz parkinga => cijene se za stanovnike ne broje

 

 

 

Faza 5 (1.0):

Dodatne funkcionalnosti koje bi se dodale u finalnoj verziji aplikacije:

                              Voditelj parkirališta:

o   voditelj parkirališta može određena mjesta posebno označiti (npr. rezervirano za stanovnika, rezervirano za invalide…)

o   neka mjesta imaju posebne cijene (kao npr. bliže zgradi je skuplje, možda dodati za 1.0)

o   za parkove za parking definira i povezuje senzore, rampe i druge odgovarajuće uređaje sa odgovarajućim mjestima na parkingu, tako da imaju pristup API-u

 

o   sigurnost, voditelj se logira sa odgovarajućim credentials-ima

 

                              Osoba koja parkira:

o   Mobilna aplikacija ima “where is my car” funkciju, gdje za svako mjesto pamti registraciju auta pa osoba može pronaći svoju registraciju i broj parking mjesta

o   Prilikom izrade korisničkog računa, korisnik dodaje registracijsku oznaku svojeg auta/svojih autiju
