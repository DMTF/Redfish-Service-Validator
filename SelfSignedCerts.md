Copyright 2018 Distributed Management Task Force, Inc. All rights reserved.

# Self-signed Certificate Walkthrough


## Introduction

The Redfish Service Validator (as well as several of the other tools in the [DMTF github organization](https://github.com/DMTF)) use the `requests` Python package for sending HTTP requests to a Redfish service. The `requests` package provides a feature to facilitate communicating with services that are protected with a server certificate that is self-signed or signed by a certificate authority (CA) that is not included in standard CA bundles.

Users of the Redfish Service Validator can make use this feature by specifying their own certificate bundle via the `--ca_bundle` command-line parameter:

```
--ca_bundle CA_BUNDLE    path to Certificate Authority bundle file or directory
```

The bundle can also be specified via the `CertificateBundle = CA_BUNDLE` option in the `config.ini` file.

While specifying the bundle to use is quite simple, creating the bundle to be used can be more challenging. This document provides one possible set of steps to create a bundle for use with the Redfish Service Validator (or any other tool/code that takes a certificate bundle as an option).  

## Steps

Steps to create a certificate bundle directory that works with the [verify=CA_BUNDLE option](http://docs.python-requests.org/en/master/user/advanced/#ssl-cert-verification) in the python `requests` library:

The steps below use a couple of commands from the openssl package. If it's not already installed on your system, go ahead and find and install it.

The steps here also assume you already have a Redfish service up and running that uses a self-signed cert.

**Step 1.** Get the certificate for your service into a PEM format file.

If you were the one that generated your self-signed cert, you may already have this at hand. But if not, you can get it from the running service using openssl. Run this openssl command, substituting the proper IP address and port for your service:

```
$ openssl s_client -connect <IP_ADDRESS>:<PORT> -showcerts
```

This will generate a couple (or a few) screenfuls of output. Scroll back through the output and look for a block of text that begins with "-----BEGIN CERTIFICATE-----" and ends with "-----END CERTIFICATE-----". Copy that text (including the  "-----BEGIN CERTIFICATE-----" and "-----END CERTIFICATE-----" lines) and paste them into a text file. Name the text file with a '.pem' extension, for example, `myhost.pem`.

**Step 2.** Place the file into a directory you will use for your ca_bundle directory for self-signed certs.

For this example, I'll use a directory called `/tmp/ca_certs` and a PEM file called `myhost.pem` (from Step 1).

```
$ mkdir /tmp/ca_certs
$ cp myhost.pem /tmp/ca_certs/
$ ls /tmp/ca_certs/
myhost.pem
```

**Step 3.** Rehash the ca_certs directory. 

This is the step that makes your ca_certs directory recognized as a CA_BUNDLE directory that can be used by various runtimes to validate server certificates.

```
$ c_rehash /tmp/ca_certs/
Doing /tmp/ca_certs/
$ ls /tmp/ca_certs/
889897a9.0 myhost.pem
```

You'll notice that now an additional file has been added to your `/tmp/ca_certs` directory. The name of the file is a based on a hash of the public cert in the .pem file.

Note: If you have additional server certificates that you want to add to the bundle of trusted certs, simply repeat steps 1, 2 and 3 for each server certificate. They can all go into the same ca_certs bundle directory.  

**Step 4.** You _may_ need to perform this step depending on whether the hostname where your service is running matches the `CN` or one of the `Subject Alternative Name` values in your certificate.

Rerun the openssl command from Step 1 that displays the contents of your certificate. Look through the output for the `Subject Alternative Name` values (if present) or the `CN` (Common Name) value. You want to be sure the hostname you use to access the service matches one of those names.

For example, let's assume your certificate has a `CN` value of `CN=idrac`. Example:

```
$ openssl s_client -connect <IP_ADDRESS>:<PORT> -showcerts
CONNECTED(00000003)
depth=0 C = US, ST = New York, L = Metropolis, O = Acme Inc., OU = Remote Access Group, CN = idrac, emailAddress = info@example.com
...
```

You would want to be sure you specify a hostname of `idrac` when accessing the service. If that is already the correct hostname for your service, you don't need to perform this step. But if not, you may need to create an entry in your local /etc/hosts file (or equivalent) to map the IP address of your service to that hostname.

So, if the CN looks like 'CN=idrac' and the IP address of your service is 127.0.0.1, add an entry like this to your /etc/hosts: 

```
127.0.0.1   idrac
```

**Step 5.** Use the new ca_certs directory

You should now be able to use the new ca_certs dir you created with the Redfish Service Validator tool like this:

```
$ python3 RedfishServiceValidator.py -i idrac --authtype Basic -u <user> -p <password> --ca_bundle /tmp/ca_certs --payload Single /redfish/v1/Systems
```

Or in another python program using the `requests` library like this:

```
r = requests.get('https://idrac/redfish/v1', verify='/tmp/ca_certs')
```


  